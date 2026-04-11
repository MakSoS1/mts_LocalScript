from fastapi import APIRouter, Request

from app.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    client = request.app.state.client
    settings = request.app.state.settings

    ollama_ok, active_models = client.health()
    missing_required = client.missing_required_models() if ollama_ok else settings.required_models_list
    missing_optional = client.missing_optional_models() if ollama_ok else settings.optional_benchmark_models_list
    status = "ok" if ollama_ok and not missing_required else "degraded"

    return HealthResponse(
        status=status,
        ollama_ok=ollama_ok,
        active_models=active_models,
        default_model=settings.default_model,
        required_demo_model=settings.required_demo_model,
        optional_benchmark_models=settings.optional_benchmark_models_list,
        allowed_models=settings.allowed_models_list,
        missing_required_models=missing_required,
        missing_optional_models=missing_optional,
    )
