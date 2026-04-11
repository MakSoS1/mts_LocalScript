from app.core.planner import plan_task
from app.utils.extract_code import normalize_output_contract
from app.validators.task_validator import validate_task_specific


def test_planner_detects_multi_field_json() -> None:
    plan = plan_task("Добавь переменную с квадратом числа и верни JSON")
    assert plan.task_type == "multi_field_json"
    assert plan.output_contract == "json_with_lua_wrappers"
    assert "squared" in plan.output_keys


def test_normalize_does_not_force_result_key_without_confidence() -> None:
    raw = "return wf.vars.try_count_n + 1"
    normalized = normalize_output_contract(
        raw,
        "json_with_lua_wrappers",
        preferred_keys=["try_count_n"],
        force_json_wrap=False,
    )
    assert normalized == raw


def test_task_validator_flags_bad_increment_pattern() -> None:
    report = validate_task_specific("return wf.vars.try_count_n", "increment")
    assert not report.ok
    assert any(issue.code == "task_increment_missing_pattern" for issue in report.issues)
