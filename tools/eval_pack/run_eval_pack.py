from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


MANUAL_SUITES = {"no-network", "judge-lock", "gpu-offload-guard"}


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def _is_json_mode(code: str) -> bool:
    return code.strip().startswith("{")


def _mode_pass(expected_mode: str, code: str) -> bool:
    if expected_mode == "json_with_lua_wrappers":
        return _is_json_mode(code)
    if expected_mode == "raw_lua":
        return not _is_json_mode(code)
    return True


def _forbidden_pass(code: str, forbidden_patterns: list[str]) -> bool:
    lowered = code.lower()
    return all(pattern.lower() not in lowered for pattern in forbidden_patterns)


def _post_json(base_url: str, path: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any], float]:
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}{path}",
            json=payload,
            timeout=120,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code >= 400:
            return False, {"error": response.text, "status_code": response.status_code}, latency_ms
        return True, response.json(), latency_ms
    except requests.RequestException as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, {"error": str(exc)}, latency_ms


def _run_generation_case(base_url: str, case: dict[str, Any]) -> dict[str, Any]:
    ok, body, latency_ms = _post_json(base_url, "/generate", {"prompt": case["prompt"]})
    if not ok:
        return {
            "status": "failed",
            "latency_ms": round(latency_ms, 2),
            "error": body.get("error", "unknown"),
            "checks": {},
        }

    code = str(body.get("code", ""))
    mode_ok = _mode_pass(str(case.get("expected_mode", "")), code)
    forbidden_ok = _forbidden_pass(code, [str(p) for p in case.get("forbidden_patterns", [])])
    case_pass = mode_ok and forbidden_ok

    followup = str(case.get("followup_prompt", "")).strip()
    expected_after_followup = str(case.get("expected_after_followup", "")).strip()
    followup_ok = True
    followup_status = "not_applicable"
    followup_code = ""
    if followup:
        followup_ok_http, followup_body, _ = _post_json(
            base_url,
            "/agent/generate",
            {
                "prompt": case["prompt"],
                "previous_code": code,
                "feedback": followup,
            },
        )
        followup_status = "failed"
        if followup_ok_http:
            followup_status = str(followup_body.get("status", "unknown"))
            followup_code = str(followup_body.get("code", ""))
            followup_ok = expected_after_followup in followup_code if expected_after_followup else True
        else:
            followup_ok = False
        case_pass = case_pass and followup_ok

    runs = int(case.get("runs", 1) or 1)
    determinism = None
    if runs > 1:
        outputs: list[str] = [code]
        format_passes = 1 if mode_ok and forbidden_ok else 0
        for _ in range(runs - 1):
            ok_more, body_more, _ = _post_json(base_url, "/generate", {"prompt": case["prompt"]})
            if not ok_more:
                continue
            more_code = str(body_more.get("code", ""))
            outputs.append(more_code)
            if _mode_pass(str(case.get("expected_mode", "")), more_code) and _forbidden_pass(
                more_code, [str(p) for p in case.get("forbidden_patterns", [])]
            ):
                format_passes += 1
        counts = Counter(outputs)
        most_common = counts.most_common(1)[0][1] if counts else 0
        determinism = {
            "runs": runs,
            "identical_ratio": round(most_common / max(len(outputs), 1), 4),
            "format_valid_ratio": round(format_passes / max(len(outputs), 1), 4),
        }

    return {
        "status": "passed" if case_pass else "failed",
        "latency_ms": round(latency_ms, 2),
        "checks": {
            "mode_pass": mode_ok,
            "forbidden_pass": forbidden_ok,
            "followup_pass": followup_ok,
        },
        "response_status": "generated",
        "code": code,
        "followup_status": followup_status,
        "followup_code": followup_code,
        "determinism": determinism,
    }


def _run_ambiguity_case(base_url: str, case: dict[str, Any]) -> dict[str, Any]:
    ok, body, latency_ms = _post_json(
        base_url,
        "/agent/generate",
        {
            "prompt": case["prompt"],
            "mode": "clarify_then_generate",
        },
    )
    if not ok:
        return {
            "status": "failed",
            "latency_ms": round(latency_ms, 2),
            "error": body.get("error", "unknown"),
            "checks": {},
        }

    status = str(body.get("status", ""))
    acceptable = [str(x) for x in body.get("acceptable_assumptions", [])]
    expected_assumptions = [str(x) for x in case.get("acceptable_assumptions", [])]
    assumptions_ok = any(item in acceptable for item in expected_assumptions) if expected_assumptions else True
    clarify_ok = status == "clarification_required" and assumptions_ok and bool(body.get("question"))

    return {
        "status": "passed" if clarify_ok else "failed",
        "latency_ms": round(latency_ms, 2),
        "checks": {
            "clarify_pass": clarify_ok,
            "assumptions_pass": assumptions_ok,
        },
        "response_status": status,
        "question": body.get("question"),
        "acceptable_assumptions": acceptable,
    }


def run_eval_pack(base_url: str, dataset: Path, output_dir: Path) -> dict[str, Any]:
    items = _load_dataset(dataset)
    run_id = datetime.now(timezone.utc).strftime("eval-pack-%Y%m%d-%H%M%S")
    results: list[dict[str, Any]] = []
    suite_stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "skipped": 0})

    for case in items:
        suite = str(case.get("suite", "unknown"))
        case_id = str(case.get("id", "unknown"))
        suite_stats[suite]["total"] += 1

        if suite in MANUAL_SUITES:
            result = {
                "id": case_id,
                "suite": suite,
                "status": "skipped",
                "reason": "manual suite",
                "checks": {},
            }
            suite_stats[suite]["skipped"] += 1
            results.append(result)
            continue

        should_clarify = bool(case.get("should_clarify", False))
        if should_clarify:
            exec_result = _run_ambiguity_case(base_url, case)
        else:
            exec_result = _run_generation_case(base_url, case)

        status = exec_result["status"]
        suite_stats[suite][status] += 1
        results.append(
            {
                "id": case_id,
                "suite": suite,
                "expected_mode": case.get("expected_mode"),
                **exec_result,
            }
        )

    total_cases = len(items)
    passed = sum(1 for item in results if item["status"] == "passed")
    failed = sum(1 for item in results if item["status"] == "failed")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    scored_total = max(total_cases - skipped, 1)
    summary = {
        "total_cases": total_cases,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / scored_total, 4),
        "base_url": base_url,
    }

    payload = {
        "run_id": run_id,
        "summary": summary,
        "suites": suite_stats,
        "cases": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Eval Pack Report: {run_id}",
        "",
        f"- Base URL: `{base_url}`",
        f"- Total: `{summary['total_cases']}`",
        f"- Passed: `{summary['passed']}`",
        f"- Failed: `{summary['failed']}`",
        f"- Skipped: `{summary['skipped']}`",
        f"- Pass rate (non-skipped): `{summary['pass_rate']}`",
        "",
        "## Suites",
        "",
        "| Suite | Total | Passed | Failed | Skipped |",
        "|---|---:|---:|---:|---:|",
    ]

    for suite, stats in sorted(suite_stats.items(), key=lambda item: item[0]):
        lines.append(
            f"| {suite} | {stats['total']} | {stats['passed']} | {stats['failed']} | {stats['skipped']} |"
        )

    lines.extend(["", "## Cases", ""])
    for item in results:
        lines.append(f"### {item['id']}")
        lines.append(f"- Suite: `{item['suite']}`")
        lines.append(f"- Status: `{item['status']}`")
        if "latency_ms" in item:
            lines.append(f"- Latency (ms): `{item['latency_ms']}`")
        checks = item.get("checks", {})
        if checks:
            lines.append(f"- Checks: `{json.dumps(checks, ensure_ascii=False)}`")
        if item.get("response_status"):
            lines.append(f"- Response status: `{item['response_status']}`")
        if item.get("reason"):
            lines.append(f"- Reason: `{item['reason']}`")
        determinism = item.get("determinism")
        if determinism:
            lines.append(f"- Determinism: `{json.dumps(determinism, ensure_ascii=False)}`")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    payload["report_json"] = str(json_path)
    payload["report_markdown"] = str(md_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extended eval pack outside submission pipeline")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--dataset", default="tools/eval_pack/dataset.jsonl")
    parser.add_argument("--output-dir", default="tools/eval_pack/reports")
    args = parser.parse_args()

    payload = run_eval_pack(
        base_url=args.base_url,
        dataset=Path(args.dataset),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(payload["report_json"])
    print(payload["report_markdown"])


if __name__ == "__main__":
    main()
