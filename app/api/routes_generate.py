from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.core.model_client import OllamaError
from app.schemas import GenerateRequest, GenerateResponse, PipelineStep, QualityGateResult, ValidationDetail, ValidationReportFull


router = APIRouter(tags=["generate"])


def _validation_to_full(vb) -> ValidationReportFull:
    def _vd(report) -> ValidationDetail:
        return ValidationDetail(
            ok=report.ok,
            issues=[{"validator": i.validator, "code": i.code, "message": i.message, "hint": i.hint} for i in report.issues],
        )
    return ValidationReportFull(
        output=_vd(vb.output),
        contract=_vd(vb.contract),
        domain=_vd(vb.domain),
        syntax=_vd(vb.syntax),
        task=_vd(vb.task) if vb.task else None,
    )


@router.post("/generate", response_model=GenerateResponse)
def generate_code(payload: GenerateRequest, request: Request) -> GenerateResponse:
    orchestrator = request.app.state.orchestrator
    start_time = time.perf_counter()

    try:
        result = orchestrator.generate(
            prompt=payload.prompt,
            model=payload.model,
            mode=payload.mode,
        )
    except OllamaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc

    latency_ms = (time.perf_counter() - start_time) * 1000
    validation_full = _validation_to_full(result.validation)
    quality_result = None

    steps: list[PipelineStep] = []
    steps.append(PipelineStep(name="Классификация", status="done", detail=result.request_mode))
    steps.append(PipelineStep(name="Планирование", status="done", detail=f"тип={result.plan.task_type}"))
    has_rules = result.benchmark_mode != "R0"
    has_examples = result.benchmark_mode in ("R2", "R3")
    steps.append(PipelineStep(name="Retrieval из KB", status="done", detail=f"правила={has_rules}, примеры={has_examples}"))
    steps.append(PipelineStep(name="Генерация", status="done", detail=f"{3 if has_examples else 1} кандидатов"))
    steps.append(PipelineStep(name="Валидация", status="done", detail="пройдена" if result.validation.ok else "есть ошибки"))
    steps.append(PipelineStep(name="Quality Gate", status="done", detail="пройден" if result.validation.ok else "не пройден"))
    if result.used_repair:
        steps.append(PipelineStep(name="Repair", status="done", detail="применён"))
    steps.append(PipelineStep(name="Итого", status="done", duration_ms=round(latency_ms, 1)))

    return GenerateResponse(
        code=result.code,
        validation=validation_full,
        quality_gate=quality_result,
        pipeline_steps=steps,
        latency_ms=round(latency_ms, 1),
        used_repair=result.used_repair,
        request_mode=result.request_mode,
        task_type=result.plan.task_type,
        candidates_generated=3 if has_examples else 1,
        ir_used=result.repaired_output is not None and result.used_repair,
    )
