import re

from .types import ValidationIssue, ValidationReport


JSONPATH_PATTERNS = [
    re.compile(r"\$\."),
    re.compile(r"\[\?\("),
    re.compile(r"jsonpath", re.IGNORECASE),
]

FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"\bwf\.variables\b", re.IGNORECASE),
    re.compile(r"\bwf\.var\b", re.IGNORECASE),
    re.compile(r"\bwf\.init\.", re.IGNORECASE),
]

FORBIDDEN_HELPERS = [
    re.compile(r"\bjsonpath\."),
    re.compile(r"\bwf\.getvar\("),
    re.compile(r"\barray_create\("),
    re.compile(r"\bsafearray\("),
]

PROMPT_PATH_RE = re.compile(r"wf\.(?:vars|initVariables)\.[A-Za-z0-9_.]+")

ALLOWED_UTILS = {
    "array.new",
    "array.markAsArray",
}


def validate_domain(code: str, prompt: str) -> ValidationReport:
    issues: list[ValidationIssue] = []
    lowered = code.lower()
    prompt_lowered = prompt.lower()

    for pattern in JSONPATH_PATTERNS:
        if pattern.search(code):
            issues.append(
                ValidationIssue(
                    code="jsonpath_forbidden",
                    message="JsonPath usage is forbidden for this domain",
                    hint="Use direct field access via wf.vars or wf.initVariables.",
                    validator="domain",
                )
            )
            break

    for pattern in FORBIDDEN_PATH_PATTERNS:
        if pattern.search(code):
            issues.append(
                ValidationIssue(
                    code="wrong_wf_path",
                    message="Detected unsupported wf path variant",
                    hint="Use only wf.vars.* and wf.initVariables.* paths.",
                    validator="domain",
                )
            )
            break

    for pattern in FORBIDDEN_HELPERS:
        if pattern.search(lowered):
            issues.append(
                ValidationIssue(
                    code="forbidden_non_domain_helper",
                    message="Detected helper API not supported in LocalScript domain",
                    hint="Do not use jsonpath/wf.getVar/custom helpers.",
                    validator="domain",
                )
            )
            break

    for match in re.findall(r"_utils\.([A-Za-z0-9_.]+)", code):
        if match not in ALLOWED_UTILS:
            issues.append(
                ValidationIssue(
                    code="forbidden_utils_call",
                    message=f"_utils.{match} is not in allowed helper list",
                    hint="Use only _utils.array.new and _utils.array.markAsArray.",
                    validator="domain",
                )
            )

    domain_prompt = prompt.lower()
    expects_lowcode = any(
        token in domain_prompt
        for token in ("wf.vars", "wf.initvariables", "lowcode", "localscript", "workflow")
    )
    if expects_lowcode and ("wf.vars" not in lowered and "wf.initvariables" not in lowered):
        issues.append(
            ValidationIssue(
                code="missing_wf_access",
                message="Expected wf.vars/wf.initVariables access for LowCode task",
                hint="Reference input fields through wf.vars or wf.initVariables.",
                validator="domain",
            )
        )

    prompt_paths = [p.lower() for p in PROMPT_PATH_RE.findall(prompt)]
    if prompt_paths and not any(path in lowered for path in prompt_paths):
        issues.append(
            ValidationIssue(
                code="missing_target_path",
                message="Prompt contains explicit wf path(s), but output does not reference them",
                hint="Use exact wf.vars/wf.initVariables path from task context.",
                validator="domain",
            )
        )

    if "require(" in lowered:
        issues.append(
            ValidationIssue(
                code="forbidden_require",
                message="External module loading is not allowed in this runtime",
                hint="Use built-in Lua and allowed helper APIs only.",
                validator="domain",
            )
        )

    if re.search(r"\bsum\s*\(", lowered) and not re.search(r"(local\s+sum\b|function\s+sum\b)", lowered):
        issues.append(
            ValidationIssue(
                code="unknown_sum_helper",
                message="Detected non-standard sum(...) helper which is not available in Lua runtime",
                hint="Use a loop with tonumber(...) and accumulate into a local total variable.",
                validator="domain",
            )
        )

    if ("active" in prompt_lowered or "активн" in prompt_lowered) and (
        "status" in prompt_lowered or "lead" in prompt_lowered or "заявк" in prompt_lowered
    ):
        if "status" not in lowered or "\"active\"" not in lowered and "'active'" not in lowered:
            issues.append(
                ValidationIssue(
                    code="missing_status_active_filter",
                    message="Prompt requires active-status filter but code does not enforce status == active",
                    hint="Filter records by status == \"active\" (or equivalent active state) before returning.",
                    validator="domain",
                )
            )

    if re.search(r"\bnext\s*\([^,]+,\s*\d+\s*\)", lowered):
        issues.append(
            ValidationIssue(
                code="risky_next_numeric_key",
                message="Detected next(table, numeric_key) pattern that may crash on non-array tables",
                hint="Avoid next(table, 1); check array shape via pairs/type(key) or explicit index checks.",
                validator="domain",
            )
        )

    if ("иначе false" in prompt_lowered or "otherwise false" in prompt_lowered) and "return {" in lowered:
        issues.append(
            ValidationIssue(
                code="boolean_expected_table_return",
                message="Prompt expects boolean true/false result, but code returns a table",
                hint="Return a boolean value directly, not an object/table wrapper.",
                validator="domain",
            )
        )

    if any(token in prompt_lowered for token in ("sum", "суммар", "общий")) and "weight" in prompt_lowered:
        if "tonumber" not in lowered:
            issues.append(
                ValidationIssue(
                    code="missing_tonumber_weight",
                    message="Weight aggregation should convert values to numbers safely",
                    hint="Use tonumber(...) with nil checks before adding weight values.",
                    validator="domain",
                )
            )

    return ValidationReport(ok=not issues, issues=issues)
