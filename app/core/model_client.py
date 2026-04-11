from __future__ import annotations

from dataclasses import dataclass

import requests

from app.config import Settings


class OllamaError(RuntimeError):
    pass


@dataclass(slots=True)
class ChatResult:
    content: str
    prompt_eval_count: int | None = None
    eval_count: int | None = None


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _urls(self, path: str) -> list[str]:
        return [f"{base.rstrip('/')}{path}" for base in self.settings.ollama_base_urls_list]

    def _post(self, path: str, payload: dict) -> dict:
        errors: list[str] = []
        for url in self._urls(path):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.settings.ollama_timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                errors.append(f"{url} -> {exc}")
                continue

        joined = "; ".join(errors) if errors else "unknown error"
        raise OllamaError(f"Ollama request failed on all endpoints: {joined}")

    def _get(self, path: str) -> dict:
        errors: list[str] = []
        for url in self._urls(path):
            try:
                response = requests.get(url, timeout=self.settings.ollama_timeout_seconds)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                errors.append(f"{url} -> {exc}")
                continue

        joined = "; ".join(errors) if errors else "unknown error"
        raise OllamaError(f"Ollama request failed on all endpoints: {joined}")

    def ensure_model_allowed(self, model: str) -> None:
        if model not in self.settings.allowed_models_list:
            raise OllamaError(
                f"Model '{model}' is not in allow-list: {self.settings.allowed_models_list}"
            )

    def list_models(self) -> list[str]:
        payload = self._get("/api/tags")
        models = payload.get("models", [])
        names: list[str] = []
        for item in models:
            name = item.get("name")
            if name:
                names.append(name)
        return names

    def running_models(self) -> list[str]:
        payload = self._get("/api/ps")
        models = payload.get("models", [])
        return [m.get("name") for m in models if m.get("name")]

    def missing_required_models(self) -> list[str]:
        installed = set(self.list_models())
        missing: list[str] = []
        for model in self.settings.required_models_list:
            if model not in installed:
                missing.append(model)
        return missing

    def missing_optional_models(self) -> list[str]:
        installed = set(self.list_models())
        missing: list[str] = []
        for model in self.settings.optional_benchmark_models_list:
            if model not in installed:
                missing.append(model)
        return missing

    def health(self) -> tuple[bool, list[str]]:
        try:
            running = self.running_models()
            return True, running
        except OllamaError:
            return False, []

    def chat(self, model: str, messages: list[dict], options: dict | None = None) -> ChatResult:
        self.ensure_model_allowed(model)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options
            or {
                "num_ctx": 4096,
                "num_predict": 256,
                "temperature": 0.1,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.05,
            },
        }
        body = self._post("/api/chat", payload)
        message = body.get("message", {})

        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama chat response does not contain message.content")

        return ChatResult(
            content=content,
            prompt_eval_count=body.get("prompt_eval_count"),
            eval_count=body.get("eval_count"),
        )
