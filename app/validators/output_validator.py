import json
import re

from .types import ValidationIssue, ValidationReport


PROSE_PREFIXES = (
    "here is",
    "вот",
    "конечно",
    "sure",
    "lua code",
)

LUA_WRAPPER_RE = re.compile(r"^lua\{([\s\S]*)\}lua$")


def _collect_wrapped_chunks(payload: object) -> list[str]:
    chunks: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            chunks.extend(_collect_wrapped_chunks(value))
        return chunks
    if isinstance(payload, list):
        for value in payload:
            chunks.extend(_collect_wrapped_chunks(value))
        return chunks
    if isinstance(payload, str):
        match = LUA_WRAPPER_RE.match(payload.strip())
        if match:
            chunks.append(match.group(1))
    return chunks


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

    # All snippets must produce a value for the wrapper contract/runtime.
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None

        if payload is not None:
            chunks = _collect_wrapped_chunks(payload)
            if chunks and any("return" not in chunk.lower() for chunk in chunks):
                issues.append(
                    ValidationIssue(
                        code="missing_return",
                        message="Lua wrapper snippet does not contain explicit return",
                        hint="Return the final value explicitly from lua{...}lua snippet.",
                        validator="output",
                    )
                )
    else:
        chunk = stripped
        match = LUA_WRAPPER_RE.match(chunk)
        if match:
            chunk = match.group(1)
        if "return" not in chunk.lower():
            issues.append(
                ValidationIssue(
                    code="missing_return",
                    message="Lua output does not contain explicit return",
                    hint="Return the final computed value explicitly.",
                    validator="output",
                )
            )

    return ValidationReport(ok=not issues, issues=issues)
