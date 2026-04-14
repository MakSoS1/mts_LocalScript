from fastapi import APIRouter, Request


router = APIRouter(tags=["models"])


@router.get("/models")
def list_models(request: Request) -> dict:
    client = request.app.state.client
    settings = request.app.state.settings

    installed = client.list_models()
    missing_required = client.missing_required_models()
    missing_optional = client.missing_optional_models()
    return {
        "required_demo_model": settings.required_demo_model,
        "optional_benchmark_models": settings.optional_benchmark_models_list,
        "allowed_models": settings.allowed_models_list,
        "installed_models": installed,
        "missing_required_models": missing_required,
        "missing_optional_models": missing_optional,
    }
