from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.core.model_client import OllamaClient
from app.core.orchestrator import Orchestrator
from app.core.retrieval import LocalRetriever
from app.benchmark.reports import write_json_report, write_markdown_report
from app.benchmark.scoring import score_case


def _load_dataset(path: Path) -> list[dict]:
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def _summary(model: str, mode: str, cases: list[dict]) -> dict:
    total = len(cases)
    if total == 0:
        return {
            "total_cases": 0,
            "avg_total_score": 0.0,
            "semantic_pass_rate": 0.0,
            "domain_pass_rate": 0.0,
            "syntax_pass_rate": 0.0,
            "format_pass_rate": 0.0,
            "avg_latency_ms": 0.0,
        }

    sum_score = sum(float(c["score"]["total_score"]) for c in cases)
    sum_latency = sum(float(c["latency_ms"]) for c in cases)

    semantic = sum(1 for c in cases if c["score"]["semantic_pass"])
    domain = sum(1 for c in cases if c["score"]["domain_pass"])
    syntax = sum(1 for c in cases if c["score"]["syntax_pass"])
    fmt = sum(1 for c in cases if c["score"]["format_pass"])

    return {
        "total_cases": total,
        "avg_total_score": round(sum_score / total, 2),
        "semantic_pass_rate": round(semantic / total, 4),
        "domain_pass_rate": round(domain / total, 4),
        "syntax_pass_rate": round(syntax / total, 4),
        "format_pass_rate": round(fmt / total, 4),
        "avg_latency_ms": round(sum_latency / total, 2),
    }


def run_benchmark(model: str, dataset_path: str, mode: str = "R3") -> dict:
    settings = get_settings()
    client = OllamaClient(settings)
    retriever = LocalRetriever(settings)
    orchestrator = Orchestrator(settings, client, retriever)

    dataset = _load_dataset(Path(dataset_path))
    run_id = datetime.now(timezone.utc).strftime("benchmark-%Y%m%d-%H%M%S")
    case_results: list[dict] = []

    for case in dataset:
        prompt = str(case["prompt"])
        start = time.perf_counter()
        result = orchestrator.generate(prompt, model=model, mode=mode)
        latency_ms = (time.perf_counter() - start) * 1000.0

        score = score_case(case, result, latency_ms)
        issues = [
            {
                "validator": i.validator,
                "code": i.code,
                "message": i.message,
                "hint": i.hint,
            }
            for i in result.validation.all_issues
        ]

        case_results.append(
            {
                "id": case.get("id", "unknown"),
                "prompt": prompt,
                "plan": {
                    "task_type": result.plan.task_type,
                    "output_contract": result.plan.output_contract,
                    "target_paths": result.plan.target_paths,
                    "needs_clarification": result.plan.needs_clarification,
                    "assumptions": result.plan.assumptions,
                    "output_keys": result.plan.output_keys,
                    "confidence": result.plan.confidence,
                },
                "raw_output": result.raw_output,
                "repaired_output": result.repaired_output,
                "output": result.code,
                "latency_ms": round(latency_ms, 2),
                "score": score,
                "validator_errors": issues,
            }
        )

    summary = _summary(model, mode, case_results)
    payload = {
        "run_id": run_id,
        "model": model,
        "mode": mode,
        "summary": summary,
        "cases": case_results,
    }

    json_report = write_json_report(settings.reports_path, run_id, payload)
    md_report = write_markdown_report(settings.reports_path, run_id, payload)

    payload["report_json"] = str(json_report)
    payload["report_markdown"] = str(md_report)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LocalScript benchmark")
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--mode", default="R3")
    args = parser.parse_args()

    result = run_benchmark(model=args.model, dataset_path=args.dataset, mode=args.mode)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(result["report_json"])
    print(result["report_markdown"])


if __name__ == "__main__":
    main()
