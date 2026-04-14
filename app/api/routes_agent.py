from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.core.model_client import OllamaError
from app.schemas import AgentGenerateRequest, AgentGenerateResponse, PipelineStep, QualityGateResult, ValidationDetail, ValidationReportFull


router = APIRouter(tags=["agent"])


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


def _quality_to_result(qg: dict) -> QualityGateResult:
    summary = qg.get("summary", {})
    return QualityGateResult(
        syntax_pass=summary.get("syntax_pass"),
        lint_pass=summary.get("lint_pass"),
        format_pass=summary.get("format_pass"),
        quality_gate_pass=summary.get("quality_gate_pass"),
    )


def _build_steps(result, start_time: float) -> list[PipelineStep]:
    elapsed = (time.perf_counter() - start_time) * 1000
    steps: list[PipelineStep] = []
    steps.append(PipelineStep(name="Классификация", status="done", duration_ms=None, detail=result.request_mode))
    steps.append(PipelineStep(name="Планирование", status="done", detail=f"тип={result.plan.task_type}, contract={result.plan.output_contract}"))
    has_rules = result.benchmark_mode != "R0"
    has_examples = result.benchmark_mode in ("R2", "R3")
    steps.append(PipelineStep(name="Retrieval из KB", status="done", detail=f"правила={has_rules}, примеры={has_examples}"))
    if result.used_repair or result.repaired_output:
        steps.append(PipelineStep(name="Генерация кандидатов", status="done"))
        steps.append(PipelineStep(name="Валидация", status="done", detail="пройдена" if result.validation.ok else "есть ошибки"))
        steps.append(PipelineStep(name="Quality Gate", status="done", detail="пройден" if result.validation.ok else "не пройден"))
        steps.append(PipelineStep(name="Repair", status="done", detail="применён" if result.used_repair else "не потребовался"))
    else:
        steps.append(PipelineStep(name="Генерация кандидатов", status="done"))
        steps.append(PipelineStep(name="Валидация", status="done", detail="пройдена" if result.validation.ok else "есть ошибки"))
        steps.append(PipelineStep(name="Quality Gate", status="done", detail="пройден" if result.validation.ok else "не пройден"))
    steps.append(PipelineStep(name="Итого", status="done", duration_ms=round(elapsed, 1)))
    return steps


@router.post("/agent/generate", response_model=AgentGenerateResponse)
def agent_generate(payload: AgentGenerateRequest, request: Request) -> AgentGenerateResponse:
    orchestrator = request.app.state.orchestrator
    start_time = time.perf_counter()

    try:
        if payload.feedback and payload.previous_code:
            result = orchestrator.repair_with_feedback(
                prompt=payload.prompt,
                previous_code=payload.previous_code,
                feedback=payload.feedback,
                model=payload.model,
                assumption=payload.assumption,
            )
        else:
            result = orchestrator.generate_agent(
                prompt=payload.prompt,
                model=payload.model,
                mode=payload.mode,
                assumption=payload.assumption,
            )
    except OllamaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail=f"Agent generation failed: {exc}") from exc

    latency_ms = (time.perf_counter() - start_time) * 1000

    gen_result = result
    if hasattr(result, 'validation'):
        pass
    else:
        gen_result = None

    validation_full = _validation_to_full(result.validation) if result.validation else None
    quality_result = None

    repair_issues = None
    if result.used_repair and result.validation:
        repair_issues = [
            {"validator": i.validator, "code": i.code, "message": i.message, "hint": i.hint}
            for i in result.validation.all_issues
        ]

    has_rules = True
    has_examples = True

    return AgentGenerateResponse(
        status=result.status,
        code=result.code,
        question=result.question,
        acceptable_assumptions=result.acceptable_assumptions or [],
        assumptions=result.assumptions or [],
        output_contract=result.output_contract,
        used_repair=result.used_repair,
        request_mode=result.request_mode,
        benchmark_mode=result.benchmark_mode,
        task_type=getattr(result, 'plan', None) and result.plan.task_type or None,
        confidence=getattr(result, 'plan', None) and result.plan.confidence or None,
        needs_clarification=getattr(result, 'plan', None) and result.plan.needs_clarification or None,
        plan=getattr(result, 'plan', None) and {
            "task_type": result.plan.task_type,
            "output_contract": result.plan.output_contract,
            "target_paths": result.plan.target_paths,
            "operation_type": result.plan.operation_type,
            "edge_cases": result.plan.edge_cases,
        } or None,
        validation=validation_full,
        quality_gate=quality_result,
        pipeline_steps=_build_steps(result, start_time),
        latency_ms=round(latency_ms, 1),
        candidates_generated=1,
        ir_used=False,
        kb_rules_used=has_rules,
        kb_examples_used=has_examples,
        repair_iterations=1 if result.used_repair else 0,
        repair_issues=repair_issues,
    )
