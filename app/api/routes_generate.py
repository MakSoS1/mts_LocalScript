from fastapi import APIRouter, HTTPException, Request

from app.core.model_client import OllamaError
from app.schemas import GenerateRequest, GenerateResponse


router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
def generate_code(payload: GenerateRequest, request: Request) -> GenerateResponse:
    orchestrator = request.app.state.orchestrator

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

    return GenerateResponse(code=result.code)
