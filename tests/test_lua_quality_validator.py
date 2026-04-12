from types import SimpleNamespace

from app.validators.lua_quality_validator import analyze_lua_tools


def test_lua_quality_validator_reports_missing_tooling(monkeypatch) -> None:
    monkeypatch.setattr("app.validators.lua_quality_validator.shutil.which", lambda _: None)

    report = analyze_lua_tools("return 1")

    assert report["summary"]["syntax_pass"] is None
    assert report["summary"]["lint_pass"] is None
    assert report["summary"]["format_pass"] is None
    assert report["summary"]["quality_gate_pass"] is None
    assert report["chunks"][0]["syntax"]["status"] == "missing"
    assert report["chunks"][0]["lint"]["status"] == "missing"
    assert report["chunks"][0]["format"]["status"] == "missing"


def test_lua_quality_validator_runs_all_tools_when_available(monkeypatch) -> None:
    paths = {
        "luac5.4": "/fake/luac",
        "luac": "/fake/luac",
        "luacheck": "/fake/luacheck",
        "stylua": "/fake/stylua",
    }

    monkeypatch.setattr("app.validators.lua_quality_validator.shutil.which", lambda name: paths.get(name))

    def fake_run(cmd, capture_output, text, check):  # type: ignore[no-untyped-def]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.validators.lua_quality_validator.subprocess.run", fake_run)

    report = analyze_lua_tools('{"result":"lua{return wf.vars.value}lua"}')

    assert report["summary"]["syntax_pass"] is True
    assert report["summary"]["lint_pass"] is True
    assert report["summary"]["format_pass"] is True
    assert report["summary"]["quality_gate_pass"] is True
    assert report["chunks"][0]["label"] == "result"


def test_lua_quality_validator_skips_lint_and_format_after_syntax_failure(monkeypatch) -> None:
    paths = {
        "luac5.4": "/fake/luac",
        "luac": "/fake/luac",
        "luacheck": "/fake/luacheck",
        "stylua": "/fake/stylua",
    }

    monkeypatch.setattr("app.validators.lua_quality_validator.shutil.which", lambda name: paths.get(name))

    def fake_run(cmd, capture_output, text, check):  # type: ignore[no-untyped-def]
        if cmd[0] == "/fake/luac":
            return SimpleNamespace(returncode=1, stdout="", stderr="syntax error")
        raise AssertionError(f"unexpected tool execution: {cmd}")

    monkeypatch.setattr("app.validators.lua_quality_validator.subprocess.run", fake_run)

    report = analyze_lua_tools("return function(")

    assert report["summary"]["syntax_pass"] is False
    assert report["summary"]["lint_pass"] is None
    assert report["summary"]["format_pass"] is None
    assert report["summary"]["quality_gate_pass"] is False
    assert report["chunks"][0]["lint"]["status"] == "skipped"
    assert report["chunks"][0]["format"]["status"] == "skipped"
