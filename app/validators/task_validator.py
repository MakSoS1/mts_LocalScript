from __future__ import annotations

import re

from app.validators.types import ValidationIssue, ValidationReport


def _has_all(code: str, items: list[str]) -> bool:
    lowered = code.lower()
    return all(item.lower() in lowered for item in items)


KEEP_ONLY_FIELDS_WRONG_LOGIC_RE = re.compile(
    r'if\s+key\s*==\s*["\']id["\']\s+or\s+key\s*==\s*["\']entity_id["\']\s+or\s+key\s*==\s*["\']call["\']',
    re.IGNORECASE,
)
ISO_TO_UNIX_OS_TIME_STRING_RE = re.compile(
    r"os\.time\s*\(\s*wf\.initvariables\.recalltime\s*\)",
    re.IGNORECASE,
)


def validate_task_specific(code: str, task_type: str | None) -> ValidationReport:
    if not task_type or task_type == "generic":
        return ValidationReport(ok=True, issues=[])

    issues: list[ValidationIssue] = []
    lowered = code.lower()

    if task_type == "last_element" and not _has_all(lowered, ["wf.vars.emails", "#wf.vars.emails"]):
        issues.append(
            ValidationIssue(
                code="hint_last_element_missing_pattern",
                message="Suggestion: consider using wf.vars.emails[#wf.vars.emails] for last email",
                hint="Use wf.vars.emails[#wf.vars.emails] for last email.",
                validator="task",
            )
        )

    if task_type == "increment" and not _has_all(lowered, ["wf.vars.try_count_n", "+ 1"]):
        issues.append(
            ValidationIssue(
                code="hint_increment_missing_pattern",
                message="Suggestion: consider returning wf.vars.try_count_n + 1",
                hint="Return wf.vars.try_count_n + 1.",
                validator="task",
            )
        )

    if task_type == "keep_only_fields" and not _has_all(
        lowered, ["wf.vars.restbody.result", "id", "entity_id", "call"]
    ):
        issues.append(
            ValidationIssue(
                code="hint_keep_only_fields_missing_pattern",
                message="Suggestion: iterate wf.vars.RESTbody.result and keep ID/ENTITY_ID/CALL",
                hint="Iterate wf.vars.RESTbody.result and keep only ID/ENTITY_ID/CALL.",
                validator="task",
            )
        )
    if task_type == "keep_only_fields" and KEEP_ONLY_FIELDS_WRONG_LOGIC_RE.search(code):
        issues.append(
            ValidationIssue(
                code="hint_keep_only_fields_wrong_logic",
                message="Detected logic that may remove required keys instead of keeping them",
                hint="Delete keys only when they are NOT ID/ENTITY_ID/CALL.",
                validator="task",
            )
        )

    if task_type == "datum_time_to_iso" and not _has_all(
        lowered, ["wf.vars.json.idoc.zcdf_head.datum", "wf.vars.json.idoc.zcdf_head.time", "string.format"]
    ):
        issues.append(
            ValidationIssue(
                code="hint_datum_time_iso_missing_pattern",
                message="Suggestion: read DATUM/TIME from wf.vars.json.IDOC.ZCDF_HEAD and format ISO string",
                hint="Read DATUM/TIME from wf.vars.json.IDOC.ZCDF_HEAD and format ISO string.",
                validator="task",
            )
        )

    if task_type == "iso_to_unix" and not _has_all(lowered, ["wf.initvariables.recalltime", "return"]):
        issues.append(
            ValidationIssue(
                code="hint_iso_to_unix_missing_pattern",
                message="Suggestion: read wf.initVariables.recallTime and return unix timestamp",
                hint="Read wf.initVariables.recallTime and return unix timestamp.",
                validator="task",
            )
        )
    if task_type == "iso_to_unix" and ISO_TO_UNIX_OS_TIME_STRING_RE.search(code):
        issues.append(
            ValidationIssue(
                code="hint_iso_to_unix_direct_os_time",
                message="Detected direct os.time(path) conversion that ignores ISO parsing details",
                hint="Parse ISO-8601 components (including timezone) before epoch conversion.",
                validator="task",
            )
        )

    if task_type == "ensure_array" and not _has_all(
        lowered, ["wf.vars.json.idoc.zcdf_head.zcdf_packages", "ensurearray"]
    ):
        issues.append(
            ValidationIssue(
                code="hint_ensure_array_missing_pattern",
                message="Suggestion: normalize items as arrays for ZCDF_PACKAGES",
                hint="Normalize items as arrays for wf.vars.json.IDOC.ZCDF_HEAD.ZCDF_PACKAGES.",
                validator="task",
            )
        )

    if task_type == "filter_non_empty" and not _has_all(
        lowered, ["parsedcsv", "discount", "markdown"]
    ):
        issues.append(
            ValidationIssue(
                code="hint_filter_non_empty_missing_pattern",
                message="Suggestion: filter parsedCsv for non-empty Discount or Markdown",
                hint="Keep items with non-empty Discount or Markdown from parsedCsv.",
                validator="task",
            )
        )

    if task_type == "multi_field_json" and not _has_all(lowered, ["squared", "tonumber"]):
        issues.append(
            ValidationIssue(
                code="hint_multi_field_json_missing_pattern",
                message="Suggestion: return num and squared fields using tonumber and multiplication",
                hint="Return num and squared fields using tonumber and multiplication.",
                validator="task",
            )
        )

    return ValidationReport(ok=True, issues=issues)
