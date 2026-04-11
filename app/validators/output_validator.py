import re

from .types import ValidationIssue, ValidationReport


PROSE_PREFIXES = (
    "here is",
    "вот",
    "конечно",
    "sure",
    "lua code",
)


def validate_output(text: str) -> ValidationReport:
    issues: list[ValidationIssue] = []
    stripped = text.strip()

    if not stripped:
        issues.append(
            ValidationIssue(
                code="empty_output",
                message="Model returned empty response",
                hint="Return Lua code only, no empty response.",
                validator="output",
            )
        )
        return ValidationReport(ok=False, issues=issues)

    if "```" in stripped:
        issues.append(
            ValidationIssue(
                code="markdown_fence",
                message="Markdown fences are not allowed",
                hint="Remove markdown fences and return plain code.",
                validator="output",
            )
        )

    first_line = stripped.splitlines()[0].strip().lower()
    if any(first_line.startswith(prefix) for prefix in PROSE_PREFIXES):
        issues.append(
            ValidationIssue(
                code="prose_prefix",
                message="Output starts with explanatory prose",
                hint="Return only code or JSON with lua{...}lua wrappers.",
                validator="output",
            )
        )

    if re.search(r"(?i)as an ai|i can't|не могу", stripped):
        issues.append(
            ValidationIssue(
                code="policy_prose",
                message="Output contains assistant prose instead of code",
                hint="Do not include explanations, return code only.",
                validator="output",
            )
        )

    return ValidationReport(ok=not issues, issues=issues)
