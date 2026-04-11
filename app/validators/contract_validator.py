import json
import re

from .types import ValidationIssue, ValidationReport


LUA_WRAPPER_RE = re.compile(r"^lua\{[\s\S]*\}lua$")


def _collect_string_values(payload: object) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_collect_string_values(value))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(_collect_string_values(value))
    elif isinstance(payload, str):
        values.append(payload)
    return values


def validate_contract(text: str, expected_contract: str | None = None) -> ValidationReport:
    stripped = text.strip()
    issues: list[ValidationIssue] = []
    is_json = stripped.startswith("{")

    if expected_contract == "json_with_lua_wrappers" and not is_json:
        issues.append(
            ValidationIssue(
                code="json_wrapper_required",
                message="Expected JSON output with lua{...}lua wrappers, got raw Lua",
                hint="Return a JSON object where values are wrapped as lua{...}lua.",
                validator="contract",
            )
        )

    if expected_contract == "raw_lua" and is_json:
        issues.append(
            ValidationIssue(
                code="raw_lua_required",
                message="Expected raw Lua output, got JSON wrapper",
                hint="Return only raw Lua code without JSON wrapper.",
                validator="contract",
            )
        )

    if is_json:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            issues.append(
                ValidationIssue(
                    code="invalid_json",
                    message="Output looks like JSON but is not valid JSON",
                    hint="Return valid JSON or raw Lua code.",
                    validator="contract",
                )
            )
            return ValidationReport(ok=False, issues=issues)

        values = _collect_string_values(payload)
        wrapped = [v for v in values if "lua{" in v or v.endswith("}lua")]
        if expected_contract == "json_with_lua_wrappers" and not wrapped:
            issues.append(
                ValidationIssue(
                    code="missing_lua_wrappers",
                    message="JSON output does not include lua{...}lua values",
                    hint="Wrap Lua snippets in JSON values using lua{...}lua format.",
                    validator="contract",
                )
            )
        for value in wrapped:
            if not LUA_WRAPPER_RE.match(value):
                issues.append(
                    ValidationIssue(
                        code="bad_lua_wrapper",
                        message="Found malformed lua wrapper",
                        hint="Use exact wrapper format: lua{...}lua",
                        validator="contract",
                    )
                )

    return ValidationReport(ok=not issues, issues=issues)
