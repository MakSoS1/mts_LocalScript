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


def test_contract_validator_requires_json_wrapper_when_expected() -> None:
    report = validate_contract("return wf.vars.a", expected_contract="json_with_lua_wrappers")
    assert not report.ok
    assert any(issue.code == "json_wrapper_required" for issue in report.issues)


def test_contract_validator_requires_raw_lua_when_expected() -> None:
    report = validate_contract('{"x":"lua{return wf.vars.a}lua"}', expected_contract="raw_lua")
    assert not report.ok
    assert any(issue.code == "raw_lua_required" for issue in report.issues)


def test_syntax_validator_reports_missing_luac_binary() -> None:
    report = validate_syntax(
        "return 1",
        luac_binary="definitely-not-installed",
        require_luac=True,
    )
    assert not report.ok
    assert any(issue.code == "luac_missing" for issue in report.issues)


def test_syntax_validator_allows_missing_luac_in_soft_mode() -> None:
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
