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
from app.validators.lua_quality_validator import analyze_lua_tools
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


def _evaluate_runtime(
    code: str, expected_mode: str, expected_key: str | None, context: dict[str, Any]
) -> tuple[bool, Any, str | None]:
    lua_chunk, _ = _extract_lua_chunk(code, expected_mode, expected_key)
    if not lua_chunk:
        return False, None, "lua_chunk_not_found"

    lua = _lua_runtime()
    if lua is None:
        return False, None, "lupa_unavailable"

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
        return False, None, str(result)
    return True, _lua_to_py(result), None


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


def _case_records(case: dict[str, Any], variants: set[str] | None = None) -> list[tuple[str, str]]:
    prompts = case.get("prompts", {})
    records = [(name, text) for name, text in prompts.items()]
    if not variants:
        return records
    return [(name, text) for name, text in records if name in variants]


def _issue_codes(report: Any) -> list[str]:
    return [str(issue.code) for issue in report.issues]


def _evaluate_output(
    *,
    code: str,
    prompt: str,
    expected_mode: str,
    expected_key: str | None,
    expected_lua: str,
    expected_runtime: Any,
    context: dict[str, Any],
    luac_binary: str,
    luacheck_binary: str,
    stylua_binary: str,
) -> dict[str, Any]:
    output_report = validate_output(code)
    contract_report = validate_contract(code, expected_contract=expected_mode)
    domain_report = validate_domain(code, prompt)
    mode_ok = _mode_pass(expected_mode, code)
    key_ok = _key_pass(expected_mode, expected_key, code)
    lua_chunk, extracted_key = _extract_lua_chunk(code, expected_mode, expected_key)
    reference_match = bool(lua_chunk) and (_norm_code(lua_chunk) == _norm_code(expected_lua))
    quality_report = analyze_lua_tools(
        code,
        luac_binary=luac_binary,
        luacheck_binary=luacheck_binary,
        stylua_binary=stylua_binary,
    )
    syntax_pass = quality_report["summary"]["syntax_pass"]
    lint_pass = quality_report["summary"]["lint_pass"]
    format_pass = quality_report["summary"]["format_pass"]
    quality_gate_pass = quality_report["summary"]["quality_gate_pass"]

    runtime_pass = False
    runtime_value = None
    if expected_runtime is not None:
        runtime_exec_ok, runtime_value, runtime_error = _evaluate_runtime(
            code=code,
            expected_mode=expected_mode,
            expected_key=expected_key,
            context=context,
        )
        if runtime_exec_ok:
            runtime_pass = _normalize_runtime(runtime_value) == _normalize_runtime(expected_runtime)
    else:
        runtime_error = None

    passed = (
        mode_ok
        and key_ok
        and contract_report.ok
        and syntax_pass is not False
        and (runtime_pass or expected_runtime is None)
    )

    return {
        "passed": passed,
        "mode_pass": mode_ok,
        "key_pass": key_ok,
        "output_pass": output_report.ok,
        "contract_pass": contract_report.ok,
        "domain_pass": domain_report.ok,
        "syntax_pass": syntax_pass,
        "lint_pass": lint_pass,
        "format_pass": format_pass,
        "quality_gate_pass": quality_gate_pass,
        "tooling": quality_report["summary"]["tooling"],
        "tool_results": quality_report["chunks"],
        "reference_match": reference_match,
        "runtime_pass": runtime_pass,
        "runtime_value": runtime_value,
        "runtime_error": runtime_error,
        "expected_runtime": expected_runtime,
        "extracted_key": extracted_key,
        "issue_codes": {
            "output": _issue_codes(output_report),
            "contract": _issue_codes(contract_report),
            "domain": _issue_codes(domain_report),
        },
        "code": code,
    }


def _payload_rank(payload: dict[str, Any]) -> tuple[int, ...]:
    tool_failures = sum(
        1
        for key in ("syntax_pass", "lint_pass", "format_pass")
        if payload.get(key) is False
    )
    return (
        1 if payload.get("passed") else 0,
        1 if payload.get("runtime_pass") else 0,
        1 if payload.get("contract_pass") else 0,
        1 if payload.get("key_pass") else 0,
        1 if payload.get("mode_pass") else 0,
        1 if payload.get("syntax_pass") is True else 0,
        1 if payload.get("lint_pass") is True else 0,
        1 if payload.get("format_pass") is True else 0,
        -tool_failures,
        -sum(len(items) for items in payload.get("issue_codes", {}).values()),
        -len(str(payload.get("code", ""))),
    )


def _build_repair_feedback(
    payload: dict[str, Any],
    *,
    expected_mode: str,
    expected_key: str | None,
) -> str:
    lines = [
        "Исправь предыдущий код по конкретным результатам проверки.",
        f"Сохрани output contract: {expected_mode}.",
    ]
    if expected_key:
        lines.append(f"Используй output key: {expected_key}.")
    if payload.get("runtime_error"):
        lines.append(f"Runtime error: {payload['runtime_error']}")
    elif payload.get("runtime_pass") is False and payload.get("expected_runtime") is not None:
        lines.append("Код выполнился, но вернул неверный результат на тестовой фикстуре.")
        lines.append(f"Expected runtime value: {json.dumps(payload['expected_runtime'], ensure_ascii=False)}")
        lines.append(f"Actual runtime value: {json.dumps(payload.get('runtime_value'), ensure_ascii=False)}")

    for area, issues in payload.get("issue_codes", {}).items():
        if not issues:
            continue
        lines.append(f"{area} issues: {', '.join(issues)}")

    for chunk in payload.get("tool_results", []):
        for tool_name in ("syntax", "lint", "format"):
            tool = chunk[tool_name]
            if tool["status"] != "failed":
                continue
            details = tool.get("details") or f"{tool_name} failed"
            lines.append(f"{tool_name} for chunk {chunk['label']}: {details}")

    lines.append("Верни только исправленный код без пояснений.")
    return "\n".join(lines)


def _phase_outputs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs = [row["initial"] for row in rows]
    outputs.extend(row["followup"] for row in rows if row["followup"])
    return outputs


def _metric_rate(outputs: list[dict[str, Any]], field: str) -> tuple[float | None, int]:
    values = [item[field] for item in outputs if item.get(field) is not None]
    if not values:
        return None, 0
    passed = sum(1 for value in values if value is True)
    return round(passed / len(values), 4), len(values)


def run_cases(
    model: str,
    output_dir: Path,
    case_ids: set[str] | None = None,
    variants: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
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
        if limit and len(rows) >= limit:
            break
        case_id = str(case["id"])
        if case_ids and case_id not in case_ids:
            continue
        case_group = "pack1" if case_id.startswith("pack1") else "pack2"
        for variant_name, prompt in _case_records(case, variants=variants):
            if limit and len(rows) >= limit:
                break
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
            initial_payload = _evaluate_output(
                code=initial_code,
                prompt=prompt,
                expected_mode=expected_mode_initial,
                expected_key=expected_key_initial,
                expected_lua=str(case["expected_lua_initial"]).strip(),
                expected_runtime=case.get("expected_runtime_initial"),
                context=case.get("context", {}),
                luac_binary=settings.luac_binary,
                luacheck_binary=settings.luacheck_binary,
                stylua_binary=settings.stylua_binary,
            )
            current_status = initial_result.status

            if not initial_payload["passed"]:
                repair_feedback = _build_repair_feedback(
                    initial_payload,
                    expected_mode=expected_mode_initial,
                    expected_key=expected_key_initial,
                )
                repair_started = time.perf_counter()
                repair_result = orchestrator.repair_with_feedback(
                    prompt=prompt,
                    previous_code=initial_code,
                    feedback=repair_feedback,
                    model=model,
                    assumption=expected_mode_initial,
                )
                repair_latency = round((time.perf_counter() - repair_started) * 1000.0, 2)
                repaired_code = repair_result.code or initial_code
                repaired_payload = _evaluate_output(
                    code=repaired_code,
                    prompt=prompt,
                    expected_mode=expected_mode_initial,
                    expected_key=expected_key_initial,
                    expected_lua=str(case["expected_lua_initial"]).strip(),
                    expected_runtime=case.get("expected_runtime_initial"),
                    context=case.get("context", {}),
                    luac_binary=settings.luac_binary,
                    luacheck_binary=settings.luacheck_binary,
                    stylua_binary=settings.stylua_binary,
                )
                repaired_payload["repair_feedback"] = repair_feedback
                repaired_payload["repair_latency_ms"] = repair_latency
                repaired_payload["previous_attempt"] = initial_payload
                if _payload_rank(repaired_payload) > _payload_rank(initial_payload):
                    initial_payload = repaired_payload
                    initial_code = repaired_code
                    current_status = repair_result.status

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
                followup_payload = _evaluate_output(
                    code=followup_code,
                    prompt=prompt,
                    expected_mode=str(case["expected_mode_followup"]),
                    expected_key=case.get("expected_output_key_followup"),
                    expected_lua=str(case["expected_lua_followup"]).strip(),
                    expected_runtime=case.get("expected_runtime_followup"),
                    context=case.get("context", {}),
                    luac_binary=settings.luac_binary,
                    luacheck_binary=settings.luacheck_binary,
                    stylua_binary=settings.stylua_binary,
                )
                followup_payload["status"] = followup_result.status
                followup_payload["latency_ms"] = followup_latency
                followup_ok = followup_payload["passed"]

            passed = initial_payload["passed"] and followup_ok

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
                    "status": current_status,
                    "passed": passed,
                    "initial": initial_payload,
                    "followup": followup_payload,
                }
            )

    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    failed = total - passed
    outputs = _phase_outputs(rows)
    semantic_pass_rate, semantic_checked = _metric_rate(outputs, "runtime_pass")
    syntax_pass_rate, syntax_checked = _metric_rate(outputs, "syntax_pass")
    lint_pass_rate, lint_checked = _metric_rate(outputs, "lint_pass")
    format_pass_rate, format_checked = _metric_rate(outputs, "format_pass")
    quality_gate_rate, quality_gate_checked = _metric_rate(outputs, "quality_gate_pass")
    summary = {
        "total_runs": total,
        "passed_runs": passed,
        "failed_runs": failed,
        "pass_rate": round(passed / max(total, 1), 4),
        "analyzed_outputs": len(outputs),
        "semantic_pass_rate": semantic_pass_rate,
        "semantic_checked_outputs": semantic_checked,
        "syntax_pass_rate": syntax_pass_rate,
        "syntax_checked_outputs": syntax_checked,
        "lint_pass_rate": lint_pass_rate,
        "lint_checked_outputs": lint_checked,
        "format_pass_rate": format_pass_rate,
        "format_checked_outputs": format_checked,
        "quality_gate_pass_rate": quality_gate_rate,
        "quality_gate_checked_outputs": quality_gate_checked,
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
        f"- Analyzed outputs: `{summary['analyzed_outputs']}`",
        f"- Semantic pass rate: `{summary['semantic_pass_rate']}`",
        f"- Syntax pass rate: `{summary['syntax_pass_rate']}`",
        f"- Lint pass rate: `{summary['lint_pass_rate']}`",
        f"- Format pass rate: `{summary['format_pass_rate']}`",
        f"- Quality gate pass rate: `{summary['quality_gate_pass_rate']}`",
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
    parser.add_argument("--case-id", action="append", default=[], help="Run only specific case id (repeatable)")
    parser.add_argument("--variant", action="append", default=[], help="Run only specific variant, e.g. ru/en/noisy")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N case-variant runs.")
    args = parser.parse_args()

    selected_case_ids = {item.strip() for item in args.case_id if item.strip()} or None
    selected_variants = {item.strip() for item in args.variant if item.strip()} or None
    payload = run_cases(
        model=args.model,
        output_dir=Path(args.output_dir),
        case_ids=selected_case_ids,
        variants=selected_variants,
        limit=args.limit or None,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(payload["report_json"])
    print(payload["report_markdown"])


if __name__ == "__main__":
    main()
