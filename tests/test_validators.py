from app.validators.contract_validator import validate_contract
from app.validators.domain_validator import validate_domain
from app.validators.output_validator import validate_output
from app.validators.syntax_validator import validate_syntax
from app.validators.task_validator import validate_task_specific


def test_output_validator_rejects_markdown_fence() -> None:
    report = validate_output("```lua\nreturn 1\n```")
    assert not report.ok
    assert any(issue.code == "markdown_fence" for issue in report.issues)


def test_domain_validator_rejects_jsonpath() -> None:
    report = validate_domain("return $.wf.vars.a", "localscript task")
    assert not report.ok
    assert any(issue.code == "jsonpath_forbidden" for issue in report.issues)


def test_contract_validator_rejects_bad_wrapper() -> None:
    report = validate_contract('{"x":"lua{return 1}"}')
    assert not report.ok
    assert any(issue.code == "bad_lua_wrapper" for issue in report.issues)


def test_contract_validator_rejects_nested_wrapper() -> None:
    report = validate_contract('{"x":"lua{lua{return 1}lua}lua"}')
    assert not report.ok
    assert any(issue.code == "nested_lua_wrapper" for issue in report.issues)


def test_contract_validator_requires_json_wrapper_when_expected() -> None:
    report = validate_contract("return wf.vars.a", expected_contract="json_with_lua_wrappers")
    assert not report.ok
    assert any(issue.code == "json_wrapper_required" for issue in report.issues)


def test_contract_validator_requires_raw_lua_when_expected() -> None:
    report = validate_contract('{"x":"lua{return wf.vars.a}lua"}', expected_contract="raw_lua")
    assert not report.ok
    assert any(issue.code == "raw_lua_required" for issue in report.issues)


def test_syntax_validator_reports_missing_luac_binary(monkeypatch) -> None:
    monkeypatch.setattr("app.validators.syntax_validator.shutil.which", lambda _: None)
    report = validate_syntax(
        "return 1",
        luac_binary="definitely-not-installed",
        require_luac=True,
    )
    assert not report.ok
    assert any(issue.code == "luac_missing" for issue in report.issues)


def test_syntax_validator_allows_missing_luac_in_soft_mode(monkeypatch) -> None:
    monkeypatch.setattr("app.validators.syntax_validator.shutil.which", lambda _: None)
    report = validate_syntax(
        "return 1",
        luac_binary="definitely-not-installed",
        require_luac=False,
    )
    assert report.ok


def test_task_validator_flags_wrong_keep_only_fields_logic() -> None:
    code = """
result = wf.vars.RESTbody.result
for _, entry in pairs(result) do
  for key, value in pairs(entry) do
    if key == "ID" or key == "ENTITY_ID" or key == "CALL" then
      entry[key] = nil
    end
  end
end
return result
""".strip()
    report = validate_task_specific(code, "keep_only_fields")
    assert not report.ok
    assert any(issue.code == "task_keep_only_fields_wrong_logic" for issue in report.issues)


def test_task_validator_flags_direct_os_time_iso_conversion() -> None:
    report = validate_task_specific("return os.time(wf.initVariables.recallTime)", "iso_to_unix")
    assert not report.ok
    assert any(issue.code == "task_iso_to_unix_direct_os_time" for issue in report.issues)


def test_output_validator_requires_return() -> None:
    report = validate_output('{"x":"lua{local n = 1}lua"}')
    assert not report.ok
    assert any(issue.code == "missing_return" for issue in report.issues)


def test_domain_validator_rejects_unknown_sum_helper() -> None:
    report = validate_domain("return sum(wf.vars.packages.weight)", "localscript task")
    assert not report.ok
    assert any(issue.code == "unknown_sum_helper" for issue in report.issues)


def test_domain_validator_requires_active_status_filter_when_prompt_demands_it() -> None:
    prompt = "Из массива leads оставь только активные заявки, где status = active."
    report = validate_domain("return wf.vars.leads", prompt)
    assert not report.ok
    assert any(issue.code == "missing_status_active_filter" for issue in report.issues)


def test_domain_validator_requires_boolean_return_for_true_false_prompt() -> None:
    prompt = "Если условие верно, верни true, иначе false."
    report = validate_domain("return {flag = true}", prompt)
    assert not report.ok
    assert any(issue.code == "boolean_expected_table_return" for issue in report.issues)


def test_domain_validator_requires_tonumber_for_weight_sum_prompt() -> None:
    prompt = "Посчитай суммарный weight и верни результат."
    report = validate_domain("return wf.vars.packages[1].weight", prompt)
    assert not report.ok
    assert any(issue.code == "missing_tonumber_weight" for issue in report.issues)


def test_domain_validator_rejects_risky_next_numeric_usage() -> None:
    prompt = "Сделай lineItems массивом."
    report = validate_domain("if next(items, 1) == nil then return {items} end", prompt)
    assert not report.ok
    assert any(issue.code == "risky_next_numeric_key" for issue in report.issues)
