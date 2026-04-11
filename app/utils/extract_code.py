import json
import re


LUA_WRAPPER_RE = re.compile(r"^lua\{([\s\S]*)\}lua$")


def strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_code_block(text: str) -> str:
    cleaned = strip_markdown_fences(text)
    return cleaned.strip()


def maybe_parse_json(text: str) -> dict | None:
    cleaned = text.strip()
    if not cleaned.startswith("{"):
        return None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _collect_string_values(payload: object) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_collect_string_values(value))
        return values
    if isinstance(payload, list):
        for value in payload:
            values.extend(_collect_string_values(value))
        return values
    if isinstance(payload, str):
        values.append(payload)
    return values


def normalize_output_contract(
    text: str,
    output_contract: str,
    preferred_keys: list[str] | None = None,
    force_json_wrap: bool = False,
) -> str:
    cleaned = extract_code_block(text)

    if output_contract == "json_with_lua_wrappers":
        if cleaned.startswith("{"):
            return cleaned
        if force_json_wrap:
            keys = preferred_keys or []
            key = keys[0] if keys else "code"
            return json.dumps({key: f"lua{{{cleaned}}}lua"}, ensure_ascii=False)
        return cleaned

    if output_contract == "raw_lua":
        payload = maybe_parse_json(cleaned)
        if payload:
            for value in _collect_string_values(payload):
                match = LUA_WRAPPER_RE.match(value.strip())
                if match:
                    return match.group(1).strip()
        return cleaned

    return cleaned
