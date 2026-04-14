from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_agent import router as agent_router
from app.api.routes_benchmark import router as benchmark_router
from app.api.routes_generate import router as generate_router
from app.api.routes_health import router as health_router
from app.api.routes_models import router as models_router
from app.api.routes_resources import router as resources_router
from app.config import get_settings
from app.core.model_client import OllamaClient
from app.core.orchestrator import Orchestrator
from app.core.retrieval import LocalRetriever
from app.utils.logging import setup_logging


settings = get_settings()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    app.state.settings = settings
    app.state.client = OllamaClient(settings)
    app.state.retriever = LocalRetriever(settings)
    app.state.orchestrator = Orchestrator(settings, app.state.client, app.state.retriever)
    yield


app = FastAPI(title="LocalScript Agent API", version="1.0.0", lifespan=lifespan)


app.include_router(generate_router)
app.include_router(agent_router)
app.include_router(health_router)
app.include_router(models_router)
app.include_router(benchmark_router)
app.include_router(resources_router)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")


@app.get("/")
async def root():
    return FileResponse(_static_dir / "index.html")
