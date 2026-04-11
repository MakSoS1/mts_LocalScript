from fastapi import APIRouter, HTTPException, Request

from app.core.model_client import OllamaError
from app.schemas import AgentGenerateRequest, AgentGenerateResponse


router = APIRouter(tags=["agent"])


@router.post("/agent/generate", response_model=AgentGenerateResponse)
def agent_generate(payload: AgentGenerateRequest, request: Request) -> AgentGenerateResponse:
    orchestrator = request.app.state.orchestrator

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

    return AgentGenerateResponse(
        status=result.status,
        code=result.code,
        question=result.question,
        acceptable_assumptions=result.acceptable_assumptions or [],
        assumptions=result.assumptions or [],
        output_contract=result.output_contract,
        used_repair=result.used_repair,
    )
