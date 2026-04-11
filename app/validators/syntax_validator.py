import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .types import ValidationIssue, ValidationReport


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


def _validate_chunk(chunk: str, luac_path: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "snippet.lua"
        path.write_text(chunk, encoding="utf-8")
        proc = subprocess.run([luac_path, "-p", str(path)], capture_output=True, text=True)
        if proc.returncode == 0:
            return True, ""

        # Some wrappers contain expressions; try again as `return <expr>`.
        path.write_text(f"return ({chunk})", encoding="utf-8")
        proc_expr = subprocess.run([luac_path, "-p", str(path)], capture_output=True, text=True)
        if proc_expr.returncode == 0:
            return True, ""
        error = (proc.stderr or proc.stdout or proc_expr.stderr or proc_expr.stdout or "").strip()
        return False, error


def validate_syntax(
    code: str,
    luac_binary: str = "luac5.4",
    require_luac: bool = False,
) -> ValidationReport:
    issues: list[ValidationIssue] = []

    candidate = code.strip()
    luac = shutil.which(luac_binary) or shutil.which("luac")
    if luac is None:
        if not require_luac:
            return ValidationReport(ok=True, issues=[])
        issues.append(
            ValidationIssue(
                code="luac_missing",
                message="Lua compiler not found for syntax validation",
                hint="Install lua5.4 and ensure luac5.4 is available.",
                validator="syntax",
            )
        )
        return ValidationReport(ok=False, issues=issues)

    if candidate.startswith("{"):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            # JSON format problems are handled by contract validator.
            return ValidationReport(ok=True, issues=[])

        chunks = _collect_wrapped_chunks(payload)
        for chunk in chunks:
            ok, error = _validate_chunk(chunk, luac)
            if not ok:
                issues.append(
                    ValidationIssue(
                        code="lua_wrapper_syntax_error",
                        message=error or "Invalid Lua in wrapper chunk",
                        hint="Fix Lua syntax inside lua{...}lua wrapper.",
                        validator="syntax",
                    )
                )
        return ValidationReport(ok=not issues, issues=issues)

    ok, error = _validate_chunk(candidate, luac)
    if not ok:
        issues.append(
            ValidationIssue(
                code="lua_syntax_error",
                message=error or "Unknown lua syntax error",
                hint="Fix Lua syntax (balanced end/if/function, valid expressions).",
                validator="syntax",
            )
        )

    return ValidationReport(ok=not issues, issues=issues)
