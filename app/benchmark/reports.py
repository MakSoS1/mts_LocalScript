from __future__ import annotations

import json
from pathlib import Path


def write_json_report(reports_dir: Path, run_id: str, payload: dict) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{run_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_markdown_report(reports_dir: Path, run_id: str, payload: dict) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{run_id}.md"

    summary = payload["summary"]
    lines = [
        f"# Benchmark Report: {run_id}",
        "",
        f"- Model: `{payload['model']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Cases: `{summary['total_cases']}`",
        f"- Avg total score: `{summary['avg_total_score']}`",
        f"- Semantic pass rate: `{summary['semantic_pass_rate']}`",
        f"- Domain pass rate: `{summary['domain_pass_rate']}`",
        f"- Syntax pass rate: `{summary['syntax_pass_rate']}`",
        f"- Format pass rate: `{summary['format_pass_rate']}`",
        f"- Avg latency (ms): `{summary['avg_latency_ms']}`",
        "",
        "## Cases",
        "",
    ]

    for case in payload["cases"]:
        lines.extend(
            [
                f"### {case['id']}",
                f"- Score: `{case['score']['total_score']}`",
                f"- Latency (ms): `{case['latency_ms']}`",
                f"- Semantic: `{case['score']['semantic_pass']}`",
                f"- Domain: `{case['score']['domain_pass']}`",
                f"- Syntax: `{case['score']['syntax_pass']}`",
                f"- Format: `{case['score']['format_pass']}`",
                "",
                "```text",
                case["output"],
                "```",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
