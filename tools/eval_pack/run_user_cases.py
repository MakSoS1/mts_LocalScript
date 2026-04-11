from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings
from app.core.model_client import OllamaClient
from app.core.orchestrator import Orchestrator
from app.core.retrieval import LocalRetriever
from app.validators.contract_validator import validate_contract
from app.validators.domain_validator import validate_domain
from app.validators.output_validator import validate_output
from tools.eval_pack.user_cases import FIRST_PACK_CASES, SECOND_PACK_CASES

try:
    from lupa import LuaRuntime  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    LuaRuntime = None  # type: ignore


LUA_WRAPPER_RE = re.compile(r"^lua\{([\s\S]*)\}lua$")


def _norm_code(code: str) -> str:
    return " ".join(code.split())


def _is_json_code(code: str) -> bool:
    return code.strip().startswith("{")


def _extract_json_payload(code: str) -> dict[str, Any] | None:
    if not _is_json_code(code):
        return None
    try:
        parsed = json.loads(code)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_lua_chunk(code: str, expected_mode: str, expected_key: str | None) -> tuple[str | None, str | None]:
    stripped = code.strip()
    if expected_mode == "raw_lua":
        return stripped, None

    payload = _extract_json_payload(stripped)
    if not payload:
        return None, None

    key = expected_key if expected_key in payload else None
    if key is None:
        for candidate_key, value in payload.items():
            if isinstance(value, str) and LUA_WRAPPER_RE.match(value.strip()):
                key = candidate_key
                break
    if key is None:
        return None, None

    value = payload.get(key)
    if not isinstance(value, str):
        return None, key
    match = LUA_WRAPPER_RE.match(value.strip())
    if not match:
        return None, key
    return match.group(1).strip(), key


def _lua_runtime() -> Any | None:
    if LuaRuntime is None:
        return None
    return LuaRuntime(unpack_returned_tuples=True)


def _py_to_lua(lua: Any, value: Any) -> Any:
    if isinstance(value, dict):
        table = lua.table()
        for key, nested in value.items():
            table[key] = _py_to_lua(lua, nested)
        return table
    if isinstance(value, list):
        table = lua.table()
        for idx, nested in enumerate(value, start=1):
            table[idx] = _py_to_lua(lua, nested)
        return table
    return value


def _lua_to_py(value: Any) -> Any:
    # Lupa table proxy has `keys` and `items` methods.
    if hasattr(value, "keys") and hasattr(value, "items"):
        keys = list(value.keys())
        if not keys:
            return []
        if all(isinstance(k, (int, float)) for k in keys):
            numeric_keys = [int(k) for k in keys]
            if all(float(k).is_integer() and k >= 1 for k in numeric_keys):
                max_key = max(numeric_keys)
                if sorted(numeric_keys) == list(range(1, max_key + 1)):
                    return [_lua_to_py(value[i]) for i in range(1, max_key + 1)]
        result: dict[str, Any] = {}
        for key, nested in value.items():
            result[str(key)] = _lua_to_py(nested)
        return result
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _evaluate_runtime(code: str, expected_mode: str, expected_key: str | None, context: dict[str, Any]) -> tuple[bool, Any]:
    lua_chunk, _ = _extract_lua_chunk(code, expected_mode, expected_key)
    if not lua_chunk:
        return False, None

    lua = _lua_runtime()
    if lua is None:
        return False, None

    wf_value = context.get("wf", {})
    lua.globals()["wf"] = _py_to_lua(lua, wf_value)
    lua.execute(
        """
_utils = {}
_utils.array = {}
function _utils.array.new()
  return {}
end
function _utils.array.markAsArray(t)
  if type(t) ~= "table" then
    return false
  end
  local max_index = 0
  for k, _ in pairs(t) do
    if type(k) ~= "number" then
      return false
    end
    if k <= 0 or math.floor(k) ~= k then
      return false
    end
    if k > max_index then
      max_index = k
    end
  end
  for i = 1, max_index do
    if t[i] == nil then
      return false
    end
  end
  return true
end
"""
    )
    executor = lua.eval(
        """
function(chunk)
  local f, err = load(chunk)
  if not f then
    return false, err
  end
  local ok, result = pcall(f)
  if not ok then
    return false, result
  end
  return true, result
end
"""
    )
    ok, result = executor(lua_chunk)
    if not ok:
        return False, None
    return True, _lua_to_py(result)


def _normalize_runtime(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_runtime(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_runtime(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _mode_pass(expected_mode: str, code: str) -> bool:
    is_json = _is_json_code(code)
    if expected_mode == "json_with_lua_wrappers":
        return is_json
    if expected_mode == "raw_lua":
        return not is_json
    return True


def _key_pass(expected_mode: str, expected_key: str | None, code: str) -> bool:
    if expected_mode == "raw_lua" or not expected_key:
        return True
    payload = _extract_json_payload(code)
    if payload is None:
        return False
    return expected_key in payload


def _run_generation(
    orchestrator: Orchestrator,
    prompt: str,
    model: str,
    expected_mode: str,
    expected_key: str | None,
) -> tuple[Any, int]:
    clarification_rounds = 0
    assumption = expected_mode if expected_mode in {"raw_lua", "json_with_lua_wrappers"} else None
    result = orchestrator.generate_agent(
        prompt=prompt,
        model=model,
        mode="clarify_then_generate",
        assumption=assumption,
    )
    while result.status == "clarification_required" and clarification_rounds < 2:
        clarification_rounds += 1
        result = orchestrator.generate_agent(
            prompt=prompt,
            model=model,
            mode="clarify_then_generate",
            assumption=assumption,
        )
    return result, clarification_rounds


def _case_records(case: dict[str, Any]) -> list[tuple[str, str]]:
    prompts = case.get("prompts", {})
    return [(name, text) for name, text in prompts.items()]


def run_cases(model: str, output_dir: Path) -> dict[str, Any]:
    settings = Settings(
        ollama_base_url="http://localhost:11434",
        ollama_base_urls="http://localhost:11434",
        ollama_timeout_seconds=90,
        required_demo_model=model,
        default_model=model,
        optional_benchmark_models="",
        strict_models="",
        syntax_require_luac=False,
    )
    client = OllamaClient(settings)
    retriever = LocalRetriever(settings)
    orchestrator = Orchestrator(settings, client, retriever)

    all_cases = [*FIRST_PACK_CASES, *SECOND_PACK_CASES]
    run_id = datetime.now(timezone.utc).strftime("user-cases-%Y%m%d-%H%M%S")
    rows: list[dict[str, Any]] = []
    suite_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})

    for case in all_cases:
        case_id = str(case["id"])
        case_group = "pack1" if case_id.startswith("pack1") else "pack2"
        for variant_name, prompt in _case_records(case):
            print(f"[RUN] {case_id}::{variant_name}", flush=True)
            started = time.perf_counter()
            try:
                initial_result, clarification_rounds = _run_generation(
                    orchestrator=orchestrator,
                    prompt=prompt,
                    model=model,
                    expected_mode=str(case["expected_mode_initial"]),
                    expected_key=case.get("expected_output_key_initial"),
                )
            except Exception as exc:
                latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
                suite_stats[case_group]["total"] += 1
                suite_stats[case_group]["failed"] += 1
                rows.append(
                    {
                        "id": case_id,
                        "group": case_group,
                        "variant": variant_name,
                        "latency_ms": latency_ms,
                        "clarification_rounds": 0,
                        "status": "failed",
                        "passed": False,
                        "error": str(exc),
                        "initial": {},
                        "followup": None,
                    }
                )
                continue

            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)

            initial_code = initial_result.code or ""
            expected_mode_initial = str(case["expected_mode_initial"])
            expected_key_initial = case.get("expected_output_key_initial")
            expected_lua_initial = str(case["expected_lua_initial"]).strip()
            expected_runtime_initial = case.get("expected_runtime_initial")

            output_report = validate_output(initial_code)
            contract_report = validate_contract(initial_code, expected_contract=expected_mode_initial)
            domain_report = validate_domain(initial_code, prompt)
            mode_ok = _mode_pass(expected_mode_initial, initial_code)
            key_ok = _key_pass(expected_mode_initial, expected_key_initial, initial_code)
            lua_chunk_initial, extracted_key = _extract_lua_chunk(initial_code, expected_mode_initial, expected_key_initial)
            lua_match_initial = bool(lua_chunk_initial) and (_norm_code(lua_chunk_initial) == _norm_code(expected_lua_initial))

            runtime_ok_initial = False
            runtime_value_initial = None
            if expected_runtime_initial is not None:
                runtime_exec_ok, runtime_value = _evaluate_runtime(
                    code=initial_code,
                    expected_mode=expected_mode_initial,
                    expected_key=expected_key_initial,
                    context=case.get("context", {}),
                )
                runtime_value_initial = runtime_value
                if runtime_exec_ok:
                    runtime_ok_initial = _normalize_runtime(runtime_value) == _normalize_runtime(expected_runtime_initial)

            followup_payload: dict[str, Any] | None = None
            followup_ok = True
            if case.get("followup_user") and variant_name == "ru":
                followup_started = time.perf_counter()
                followup_result = orchestrator.repair_with_feedback(
                    prompt=prompt,
                    previous_code=initial_code,
                    feedback=str(case["followup_user"]),
                    model=model,
                    assumption=case.get("expected_mode_followup"),
                )
                followup_latency = round((time.perf_counter() - followup_started) * 1000.0, 2)
                followup_code = followup_result.code or ""
                expected_mode_followup = str(case["expected_mode_followup"])
                expected_key_followup = case.get("expected_output_key_followup")
                expected_lua_followup = str(case["expected_lua_followup"]).strip()
                expected_runtime_followup = case.get("expected_runtime_followup")

                followup_mode_ok = _mode_pass(expected_mode_followup, followup_code)
                followup_key_ok = _key_pass(expected_mode_followup, expected_key_followup, followup_code)
                followup_chunk, followup_extracted_key = _extract_lua_chunk(
                    followup_code,
                    expected_mode_followup,
                    expected_key_followup,
                )
                followup_lua_match = bool(followup_chunk) and (
                    _norm_code(followup_chunk) == _norm_code(expected_lua_followup)
                )

                followup_runtime_ok = False
                followup_runtime_value = None
                if expected_runtime_followup is not None:
                    runtime_exec_ok, runtime_value = _evaluate_runtime(
                        code=followup_code,
                        expected_mode=expected_mode_followup,
                        expected_key=expected_key_followup,
                        context=case.get("context", {}),
                    )
                    followup_runtime_value = runtime_value
                    if runtime_exec_ok:
                        followup_runtime_ok = _normalize_runtime(runtime_value) == _normalize_runtime(expected_runtime_followup)

                followup_ok = (
                    followup_mode_ok
                    and followup_key_ok
                    and (followup_runtime_ok or expected_runtime_followup is None)
                )
                followup_payload = {
                    "status": followup_result.status,
                    "latency_ms": followup_latency,
                    "mode_pass": followup_mode_ok,
                    "key_pass": followup_key_ok,
                    "lua_match": followup_lua_match,
                    "runtime_pass": followup_runtime_ok,
                    "runtime_value": followup_runtime_value,
                    "expected_runtime": expected_runtime_followup,
                    "extracted_key": followup_extracted_key,
                }

            initial_ok = (
                mode_ok
                and key_ok
                and output_report.ok
                and contract_report.ok
                and domain_report.ok
                and (runtime_ok_initial or expected_runtime_initial is None)
            )
            passed = initial_ok and followup_ok

            suite_stats[case_group]["total"] += 1
            suite_stats[case_group]["passed"] += int(passed)
            suite_stats[case_group]["failed"] += int(not passed)

            rows.append(
                {
                    "id": case_id,
                    "group": case_group,
                    "variant": variant_name,
                    "latency_ms": latency_ms,
                    "clarification_rounds": clarification_rounds,
                    "status": initial_result.status,
                    "passed": passed,
                    "initial": {
                        "mode_pass": mode_ok,
                        "key_pass": key_ok,
                        "output_pass": output_report.ok,
                        "contract_pass": contract_report.ok,
                        "domain_pass": domain_report.ok,
                        "lua_match": lua_match_initial,
                        "runtime_pass": runtime_ok_initial,
                        "runtime_value": runtime_value_initial,
                        "expected_runtime": expected_runtime_initial,
                        "extracted_key": extracted_key,
                    },
                    "followup": followup_payload,
                }
            )

    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    failed = total - passed
    summary = {
        "total_runs": total,
        "passed_runs": passed,
        "failed_runs": failed,
        "pass_rate": round(passed / max(total, 1), 4),
    }
    payload = {
        "run_id": run_id,
        "model": model,
        "summary": summary,
        "suite_stats": suite_stats,
        "rows": rows,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# User Cases Report: {run_id}",
        "",
        f"- Model: `{model}`",
        f"- Total runs: `{summary['total_runs']}`",
        f"- Passed: `{summary['passed_runs']}`",
        f"- Failed: `{summary['failed_runs']}`",
        f"- Pass rate: `{summary['pass_rate']}`",
        "",
        "## Groups",
        "",
        "| Group | Total | Passed | Failed |",
        "|---|---:|---:|---:|",
    ]
    for group, stats in sorted(suite_stats.items(), key=lambda item: item[0]):
        md_lines.append(f"| {group} | {stats['total']} | {stats['passed']} | {stats['failed']} |")

    md_lines.extend(["", "## Failed Runs", ""])
    for row in rows:
        if row["passed"]:
            continue
        md_lines.append(f"### {row['id']} ({row['variant']})")
        md_lines.append(f"- Status: `{row['status']}`")
        md_lines.append(f"- Clarification rounds: `{row['clarification_rounds']}`")
        md_lines.append(f"- Initial checks: `{json.dumps(row['initial'], ensure_ascii=False)}`")
        if row["followup"]:
            md_lines.append(f"- Follow-up checks: `{json.dumps(row['followup'], ensure_ascii=False)}`")
        md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    payload["report_json"] = str(json_path)
    payload["report_markdown"] = str(md_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run user business cases through agent pipeline")
    parser.add_argument("--model", default="localscript-qwen25coder7b:latest")
    parser.add_argument("--output-dir", default="tools/eval_pack/reports")
    args = parser.parse_args()

    payload = run_cases(model=args.model, output_dir=Path(args.output_dir))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(payload["report_json"])
    print(payload["report_markdown"])


if __name__ == "__main__":
    main()
