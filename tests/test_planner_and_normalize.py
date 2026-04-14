from app.core.planner import plan_task
from app.utils.extract_code import normalize_output_contract
from app.validators.task_validator import validate_task_specific
import json


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


def test_normalize_json_renames_single_key_to_preferred() -> None:
    raw = '{"result":"lua{return 1}lua"}'
    normalized = normalize_output_contract(
        raw,
        "json_with_lua_wrappers",
        preferred_keys=["retryDelaySec"],
        force_json_wrap=False,
    )
    payload = json.loads(normalized)
    assert payload == {"retryDelaySec": "lua{return 1}lua"}


def test_task_validator_hints_bad_increment_pattern() -> None:
    report = validate_task_specific("return wf.vars.try_count_n", "increment")
    assert report.ok
    assert any(issue.code == "hint_increment_missing_pattern" for issue in report.issues)


def test_planner_prefers_raw_lua_when_explicit_wf_path_without_json_request() -> None:
    plan = plan_task("Normalize package items to arrays in wf.vars.json.IDOC.ZCDF_HEAD.ZCDF_PACKAGES.")
    assert plan.output_contract == "raw_lua"
    assert plan.target_paths == ["wf.vars.json.IDOC.ZCDF_HEAD.ZCDF_PACKAGES"]


def test_planner_prefers_json_when_no_explicit_path_and_no_output_mode() -> None:
    plan = plan_task("Добавь переменную со временем")
    assert plan.output_contract == "json_with_lua_wrappers"


def test_planner_extracts_output_key_from_ru_prompt() -> None:
    plan = plan_task("Посчитай total и верни результат в переменную retryDelaySec.")
    assert "retryDelaySec" in plan.output_keys


def test_planner_extracts_output_key_from_en_prompt() -> None:
    plan = plan_task("Build payload and return the result as notificationPayload.")
    assert "notificationPayload" in plan.output_keys


def test_planner_extracts_output_key_from_value_phrase() -> None:
    plan = plan_task("Посчитай общий вес и верни значение в totalWeight.")
    assert "totalWeight" in plan.output_keys


def test_planner_extracts_output_key_from_define_style_prompt() -> None:
    plan = plan_task("Определи approvalRoute. Если ... верни standard.")
    assert "approvalRoute" in plan.output_keys


def test_normalize_flattens_nested_lua_wrapper() -> None:
    raw = '{"code":"lua{lua{return 1}lua}lua"}'
    normalized = normalize_output_contract(
        raw,
        "json_with_lua_wrappers",
        preferred_keys=["result"],
        force_json_wrap=True,
    )
    payload = json.loads(normalized)
    assert payload == {"result": "lua{return 1}lua"}


def test_normalize_rewrites_unsupported_array_push() -> None:
    raw = '{"result":"lua{local out = _utils.array.new()\\n_utils.array.push(out, item)\\nreturn out}lua"}'
    normalized = normalize_output_contract(
        raw,
        "json_with_lua_wrappers",
        preferred_keys=["result"],
        force_json_wrap=True,
    )
    payload = json.loads(normalized)
    assert "_utils.array.push(" not in payload["result"]
    assert "table.insert(" in payload["result"]
