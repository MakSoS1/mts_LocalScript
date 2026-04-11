from fastapi import APIRouter, HTTPException

from app.benchmark.runner import run_benchmark
from app.schemas import BenchmarkRequest, BenchmarkResponse, BenchmarkSummary


router = APIRouter(tags=["benchmark"])


@router.post("/benchmark", response_model=BenchmarkResponse)
def benchmark(payload: BenchmarkRequest) -> BenchmarkResponse:
    try:
        result = run_benchmark(
            model=payload.model,
            dataset_path=payload.dataset,
            mode=payload.mode.value,
        )
    except Exception as exc:  # pragma: no cover - handled at API layer
        raise HTTPException(status_code=400, detail=f"Benchmark failed: {exc}") from exc

    summary = BenchmarkSummary(**result["summary"])
    return BenchmarkResponse(
        run_id=result["run_id"],
        model=result["model"],
        mode=payload.mode,
        summary=summary,
        report_json=result["report_json"],
        report_markdown=result["report_markdown"],
    )
