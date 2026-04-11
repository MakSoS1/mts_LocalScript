from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.core.planner import TaskPlan
from app.main import app
from app.validators.types import ValidationBundle, ValidationReport


class DummyOrchestrator:
    def generate(self, prompt: str, model=None, mode=None):  # noqa: ANN001
        ok = ValidationReport(ok=True, issues=[])
        bundle = ValidationBundle(output=ok, contract=ok, domain=ok, syntax=ok)
        code = "return wf.vars.emails[#wf.vars.emails]"
        return SimpleNamespace(
            code=code,
            model=model or "localscript-qwen25coder7b",
            request_mode="direct_generation",
            benchmark_mode="R3",
            raw_output=code,
            repaired_output=None,
            validation=bundle,
            used_repair=False,
            plan=TaskPlan(
                task_type="last_element",
                output_contract="json_with_lua_wrappers",
                target_paths=["wf.vars.emails"],
                needs_clarification=False,
                assumptions=[],
                output_keys=["lastEmail"],
                confidence=0.95,
            ),
        )


class DummyClient:
    def health(self):
        return True, []

    def missing_required_models(self):
        return []

    def missing_optional_models(self):
        return []


def test_generate_endpoint_returns_code() -> None:
    with TestClient(app) as client:
        app.state.orchestrator = DummyOrchestrator()
        app.state.client = DummyClient()
        response = client.post("/generate", json={"prompt": "test"})
        assert response.status_code == 200
        assert "code" in response.json()


def test_health_endpoint_schema() -> None:
    with TestClient(app) as client:
        app.state.client = DummyClient()
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert "missing_required_models" in body
        assert "missing_optional_models" in body
        assert body["status"] == "ok"
