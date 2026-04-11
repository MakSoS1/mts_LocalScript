from __future__ import annotations

import json
from pathlib import Path


def _infer_dataset(payload: dict) -> str:
    case_ids = [str(case.get("id", "")) for case in payload.get("cases", [])]
    if any(case_id.startswith("aug_") for case_id in case_ids):
        return "augmented"
    return "public"


def main() -> None:
    reports_dir = Path("app/reports")
    report_paths = sorted(reports_dir.glob("benchmark-*.json"))
    if not report_paths:
        raise SystemExit("No benchmark json reports found in app/reports")

    latest_runs: dict[tuple[str, str, str], dict] = {}
    for path in report_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        dataset = _infer_dataset(payload)
        row = {
            "run_id": str(payload.get("run_id", "")),
            "model": payload["model"],
            "mode": payload["mode"],
            "dataset": dataset,
            "avg_total_score": float(summary["avg_total_score"]),
            "semantic_pass_rate": float(summary["semantic_pass_rate"]),
            "domain_pass_rate": float(summary["domain_pass_rate"]),
            "syntax_pass_rate": float(summary["syntax_pass_rate"]),
            "format_pass_rate": float(summary["format_pass_rate"]),
            "avg_latency_ms": float(summary["avg_latency_ms"]),
            "report": str(path),
        }
        key = (row["model"], row["mode"], row["dataset"])
        previous = latest_runs.get(key)
        if previous is None or row["run_id"] > previous["run_id"]:
            latest_runs[key] = row

    rows = list(latest_runs.values())

    rows.sort(
        key=lambda r: (
            r["dataset"],
            r["mode"],
            -r["avg_total_score"],
            r["avg_latency_ms"],
        )
    )

    lines = [
        "# Comparative Report (Latest Per Model/Mode/Dataset)",
        "",
        "| Rank | Dataset | Mode | Model | Avg Score | Semantic | Domain | Syntax | Format | Avg Latency (ms) | Report |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            "| {rank} | {dataset} | {mode} | {model} | {score:.2f} | {semantic:.4f} | {domain:.4f} | {syntax:.4f} | {fmt:.4f} | {latency:.2f} | `{report}` |".format(
                rank=idx,
                dataset=row["dataset"],
                model=row["model"],
                mode=row["mode"],
                score=row["avg_total_score"],
                semantic=row["semantic_pass_rate"],
                domain=row["domain_pass_rate"],
                syntax=row["syntax_pass_rate"],
                fmt=row["format_pass_rate"],
                latency=row["avg_latency_ms"],
                report=row["report"],
            )
        )

    output = Path("comparative_report.md")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
