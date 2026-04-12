from app.benchmark.scoring import score_case
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
    }

    monkeypatch.setattr("app.benchmark.scoring.oracle_semantic_pass", lambda task_type, code: False)
    score = score_case(case, result, latency_ms=100)
    assert not score["semantic_pass"]
