from app.benchmark.scoring import score_case, semantic_pass
from app.core.orchestrator import GenerationResult
from app.core.planner import TaskPlan
from app.validators.types import ValidationBundle, ValidationReport


def _ok_bundle() -> ValidationBundle:
    ok = ValidationReport(ok=True, issues=[])
    return ValidationBundle(output=ok, contract=ok, domain=ok, syntax=ok)


def test_score_case_high_when_all_pass() -> None:
    result = GenerationResult(
        code='{"lastEmail":"lua{return wf.vars.emails[#wf.vars.emails]}lua"}',
        model="localscript-qwen25coder7b",
        request_mode="direct_generation",
        benchmark_mode="R3",
        raw_output='{"lastEmail":"lua{return wf.vars.emails[#wf.vars.emails]}lua"}',
        repaired_output=None,
        validation=_ok_bundle(),
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

    case = {
        "expected_mode": "json_with_lua_wrappers",
        "expected_contains": ["wf.vars.emails"],
        "expected_not_contains": ["jsonpath"],
    }

    score = score_case(case, result, latency_ms=100)
    assert score["semantic_pass"]
    assert score["domain_pass"]
    assert score["syntax_pass"]
    assert score["format_pass"]
    assert score["total_score"] > 90


def test_score_case_uses_oracle_result_when_available(monkeypatch) -> None:
    result = GenerationResult(
        code='{"lastEmail":"lua{return wf.vars.emails[#wf.vars.emails]}lua"}',
        model="localscript-qwen25coder7b",
        request_mode="direct_generation",
        benchmark_mode="R3",
        raw_output='{"lastEmail":"lua{return wf.vars.emails[#wf.vars.emails]}lua"}',
        repaired_output=None,
        validation=_ok_bundle(),
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

    case = {
        "id": "last_array_element",
        "expected_mode": "json_with_lua_wrappers",
        "expected_contains": ["wf.vars.emails"],
        "expected_not_contains": ["jsonpath"],
        "wf_fixture": {"wf": {"vars": {"emails": ["a@b.com", "c@d.com"]}}},
        "expected_runtime_output": "c@d.com",
        "expected_json_key": "lastEmail",
    }

    monkeypatch.setattr("app.benchmark.scoring.runtime_oracle_pass", lambda *a, **kw: (False, "mismatch"))
    score = score_case(case, result, latency_ms=100)
    assert not score["semantic_pass"]


def test_task_validator_not_hard_fail() -> None:
    from app.validators.task_validator import validate_task_specific
    code = "return normalize_items(wf.vars.emails)"
    report = validate_task_specific(code, "last_element")
    assert report.ok is True
    assert len(report.issues) > 0


def test_semantic_pass_prefers_runtime_oracle(monkeypatch) -> None:
    case = {
        "id": "test_case",
        "wf_fixture": {"wf": {"vars": {"emails": ["a@b.com"]}}},
        "expected_runtime_output": "a@b.com",
        "expected_json_key": "lastEmail",
    }
    code = '{"lastEmail": "lua{return wf.vars.emails[1]}lua"}'

    called = {}
    def mock_runtime(code, fixture, expected, key=None):
        called["yes"] = True
        return True, ""

    monkeypatch.setattr("app.benchmark.scoring.runtime_oracle_pass", mock_runtime)
    ok, detail = semantic_pass(case, code)
    assert ok is True
    assert called.get("yes") is True
