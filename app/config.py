from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_REQUIRED_DEMO_MODEL = "localscript-qwen25coder7b"
DEFAULT_OPTIONAL_BENCHMARK_MODELS: list[str] = []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_base_urls: str = "http://host.docker.internal:11434,http://localhost:11434"
    ollama_timeout_seconds: int = 180

    required_demo_model: str = DEFAULT_REQUIRED_DEMO_MODEL
    default_model: str = DEFAULT_REQUIRED_DEMO_MODEL
    optional_benchmark_models: str = Field(
        default=",".join(DEFAULT_OPTIONAL_BENCHMARK_MODELS),
        description="Comma-separated optional benchmark models.",
    )
    strict_models: str = Field(
        default="",
        description="Legacy extra allow-list. Optional.",
    )

    luac_binary: str = "luac5.4"
    syntax_require_luac: bool = False
    repair_max_passes: int = 1

    kb_dir: str = "app/kb"
    reports_dir: str = "app/reports"

    @property
    def strict_models_list(self) -> list[str]:
        return [m.strip() for m in self.strict_models.split(",") if m.strip()]

    @property
    def optional_benchmark_models_list(self) -> list[str]:
        return [m.strip() for m in self.optional_benchmark_models.split(",") if m.strip()]

    @property
    def allowed_models_list(self) -> list[str]:
        models = [self.required_demo_model, *self.optional_benchmark_models_list, *self.strict_models_list]
        deduped: list[str] = []
        for model in models:
            if model and model not in deduped:
                deduped.append(model)
        return deduped

    @property
    def required_models_list(self) -> list[str]:
        return [self.required_demo_model]

    @property
    def ollama_base_urls_list(self) -> list[str]:
        candidates = [u.strip() for u in self.ollama_base_urls.split(",") if u.strip()]
        # Backward-compatible fallback for older configs that only set OLLAMA_BASE_URL.
        if not candidates and self.ollama_base_url:
            candidates = [self.ollama_base_url.strip()]
        if not candidates:
            candidates = ["http://host.docker.internal:11434", "http://localhost:11434"]

        deduped: list[str] = []
        for url in candidates:
            if url not in deduped:
                deduped.append(url)
        return deduped

    @property
    def kb_path(self) -> Path:
        return Path(self.kb_dir)

    @property
    def reports_path(self) -> Path:
        return Path(self.reports_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
