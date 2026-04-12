from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


LUA_WRAPPER_RE = re.compile(r"^lua\{([\s\S]*)\}lua$")


def _collect_wrapped_chunks(payload: object, prefix: str = "") -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            chunks.extend(_collect_wrapped_chunks(value, label))
        return chunks
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            label = f"{prefix}[{index}]" if prefix else f"[{index}]"
            chunks.extend(_collect_wrapped_chunks(value, label))
        return chunks
    if isinstance(payload, str):
        match = LUA_WRAPPER_RE.match(payload.strip())
        if match:
            chunks.append((prefix or "value", match.group(1)))
    return chunks


def _extract_named_chunks(code: str) -> list[tuple[str, str]]:
    candidate = code.strip()
    if not candidate:
        return []
    if not candidate.startswith("{"):
        return [("raw", candidate)]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return []

    return _collect_wrapped_chunks(payload)


def _run_with_tempfile(source: str, command_builder: Any) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "snippet.lua"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        proc = subprocess.run(command_builder(path), capture_output=True, text=True, check=False)
        details = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part and part.strip())
        return proc.returncode, details


def _resolve_tool(binary: str, *fallbacks: str) -> str | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [binary, *fallbacks]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return str(path.resolve())
        if not path.is_absolute():
            repo_path = repo_root / path
            if repo_path.exists():
                return str(repo_path.resolve())
        resolved = shutil.which(value)
        if resolved:
            return resolved
    return None


def _missing_result(tool: str, binary: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "available": False,
        "ok": None,
        "status": "missing",
        "details": f"`{binary}` is not available.",
    }


def _skipped_result(tool: str, reason: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "available": True,
        "ok": None,
        "status": "skipped",
        "details": reason,
    }


def _command_result(tool: str, ok: bool, details: str | None, **extra: Any) -> dict[str, Any]:
    return {
        "tool": tool,
        "available": True,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "details": details or None,
        **extra,
    }


def _run_luac(chunk: str, luac_path: str | None, binary: str) -> tuple[dict[str, Any], str]:
    if luac_path is None:
        return _missing_result("syntax", binary), chunk

    primary_rc, primary_details = _run_with_tempfile(
        chunk,
        lambda path: [luac_path, "-p", str(path)],
    )
    if primary_rc == 0:
        return _command_result("syntax", True, None, normalized_as_expression=False), chunk

    expression_chunk = f"return ({chunk})"
    expr_rc, expr_details = _run_with_tempfile(
        expression_chunk,
        lambda path: [luac_path, "-p", str(path)],
    )
    if expr_rc == 0:
        return _command_result("syntax", True, None, normalized_as_expression=True), expression_chunk

    details = expr_details or primary_details or "Lua syntax check failed."
    return _command_result("syntax", False, details, normalized_as_expression=False), chunk


def _run_luacheck(
    prepared_chunk: str,
    luacheck_path: str | None,
    binary: str,
    globals_list: tuple[str, ...],
) -> dict[str, Any]:
    if luacheck_path is None:
        return _missing_result("lint", binary)

    rc, details = _run_with_tempfile(
        prepared_chunk,
        lambda path: [luacheck_path, str(path), "--globals", *globals_list],
    )
    return _command_result("lint", rc == 0, details)


def _run_stylua(prepared_chunk: str, stylua_path: str | None, binary: str) -> dict[str, Any]:
    if stylua_path is None:
        return _missing_result("format", binary)

    rc, details = _run_with_tempfile(
        prepared_chunk,
        lambda path: [stylua_path, "--check", str(path)],
    )
    return _command_result("format", rc == 0, details)


def _format_chunk(chunk: str, stylua_path: str) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "snippet.lua"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(chunk)
        proc = subprocess.run([stylua_path, str(path)], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return chunk
        return path.read_text(encoding="utf-8")


def _format_payload(payload: object, stylua_path: str) -> object:
    if isinstance(payload, dict):
        return {key: _format_payload(value, stylua_path) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_format_payload(value, stylua_path) for value in payload]
    if isinstance(payload, str):
        match = LUA_WRAPPER_RE.match(payload.strip())
        if not match:
            return payload
        formatted = _format_chunk(match.group(1), stylua_path)
        return f"lua{{{formatted}}}lua"
    return payload


def format_lua_code(code: str, stylua_binary: str = "stylua") -> str:
    stylua_path = _resolve_tool(stylua_binary)
    if stylua_path is None:
        return code

    candidate = code.strip()
    if not candidate:
        return code
    if not candidate.startswith("{"):
        return _format_chunk(candidate, stylua_path)

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return code

    formatted = _format_payload(payload, stylua_path)
    return json.dumps(formatted, ensure_ascii=False)


def _aggregate_tool(chunks: list[dict[str, Any]], key: str) -> bool | None:
    values = [chunk[key]["ok"] for chunk in chunks if chunk[key]["status"] not in {"missing", "skipped"}]
    if not values:
        return None
    return all(value is True for value in values)


def analyze_lua_tools(
    code: str,
    *,
    luac_binary: str = "luac5.4",
    luacheck_binary: str = "luacheck",
    stylua_binary: str = "stylua",
    globals_list: tuple[str, ...] = ("wf", "_utils"),
) -> dict[str, Any]:
    named_chunks = _extract_named_chunks(code)
    luac_path = _resolve_tool(luac_binary, "luac")
    luacheck_path = _resolve_tool(luacheck_binary)
    stylua_path = _resolve_tool(stylua_binary)

    chunks: list[dict[str, Any]] = []
    for label, chunk in named_chunks:
        syntax_result, prepared_chunk = _run_luac(chunk, luac_path, luac_binary)

        if syntax_result["ok"] is False:
            lint_result = (
                _missing_result("lint", luacheck_binary)
                if luacheck_path is None
                else _skipped_result("lint", "Skipped because Lua syntax failed.")
            )
            format_result = (
                _missing_result("format", stylua_binary)
                if stylua_path is None
                else _skipped_result("format", "Skipped because Lua syntax failed.")
            )
        else:
            lint_result = _run_luacheck(prepared_chunk, luacheck_path, luacheck_binary, globals_list)
            format_result = _run_stylua(prepared_chunk, stylua_path, stylua_binary)

        chunks.append(
            {
                "label": label,
                "preview": chunk[:160],
                "syntax": syntax_result,
                "lint": lint_result,
                "format": format_result,
            }
        )

    syntax_pass = _aggregate_tool(chunks, "syntax")
    lint_pass = _aggregate_tool(chunks, "lint")
    format_pass = _aggregate_tool(chunks, "format")

    quality_gate_pass: bool | None
    if not chunks:
        quality_gate_pass = None
    elif syntax_pass is None and lint_pass is None and format_pass is None:
        quality_gate_pass = None
    else:
        quality_gate_pass = syntax_pass is not False and lint_pass is not False and format_pass is not False

    return {
        "chunks": chunks,
        "summary": {
            "chunks_found": len(chunks),
            "syntax_pass": syntax_pass,
            "lint_pass": lint_pass,
            "format_pass": format_pass,
            "quality_gate_pass": quality_gate_pass,
            "tooling": {
                "luac": luac_path is not None,
                "luacheck": luacheck_path is not None,
                "stylua": stylua_path is not None,
            },
        },
    }
