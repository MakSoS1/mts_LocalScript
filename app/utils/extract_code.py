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


def _score_string_candidate(value: str) -> int:
    stripped = value.strip()
    score = 0
    if LUA_WRAPPER_RE.match(stripped):
        score += 100
    if "lua{" in stripped and "}lua" in stripped:
        score += 60
    lowered = stripped.lower()
    if "return" in lowered:
        score += 20
    if "wf." in lowered:
        score += 10
    score += min(len(stripped), 500) // 50
    return score


def _canonicalize_lua_wrapper(value: str) -> str:
    current = value.strip()
    for _ in range(4):
        match = LUA_WRAPPER_RE.match(current)
        if not match:
            return current

        inner = match.group(1).strip()

        # Fix nested wrappers like lua{lua{...}lua}lua.
        nested = LUA_WRAPPER_RE.match(inner)
        if nested:
            current = inner
            continue

        # Fix dangling duplicated suffix like lua{...}lua}lua.
        if inner.endswith("}lua") and "lua{" not in inner:
            inner = inner[: -len("}lua")].rstrip()
            current = f"lua{{{inner}}}lua"
            continue

        return f"lua{{{inner}}}lua"

    return current


def _maybe_wrap_lua(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "lua{return nil}lua"
    if stripped.startswith("lua{") and stripped.endswith("}lua"):
        canonical = _canonicalize_lua_wrapper(stripped)
        match = LUA_WRAPPER_RE.match(canonical)
        if not match:
            return canonical
        normalized_inner = _normalize_lua_snippet(match.group(1))
        return f"lua{{{normalized_inner}}}lua"
    return f"lua{{{_normalize_lua_snippet(stripped)}}}lua"


def _normalize_lua_snippet(snippet: str) -> str:
    normalized = snippet
    normalized = normalized.replace("_utils.array.push(", "table.insert(")
    return normalized


def normalize_output_contract(
    text: str,
    output_contract: str,
    preferred_keys: list[str] | None = None,
    force_json_wrap: bool = False,
) -> str:
    cleaned = extract_code_block(text)

    if output_contract == "json_with_lua_wrappers":
        if cleaned.startswith("{"):
            payload = maybe_parse_json(cleaned)
            if payload is None:
                return cleaned

            preferred = preferred_keys[0] if preferred_keys else None
            if preferred and preferred not in payload and payload:
                if len(payload) == 1:
                    only_key = next(iter(payload))
                    payload = {preferred: payload[only_key]}
                else:
                    string_items = [(key, value) for key, value in payload.items() if isinstance(value, str)]
                    if string_items:
                        best_key, best_value = max(string_items, key=lambda item: _score_string_candidate(item[1]))
                        payload = {preferred: best_value}
                    else:
                        payload = {preferred: next(iter(payload.values()))}

            if preferred and preferred in payload and isinstance(payload[preferred], str):
                payload[preferred] = _maybe_wrap_lua(payload[preferred])
            elif force_json_wrap and preferred:
                selected_value = payload.get(preferred)
                if isinstance(selected_value, str):
                    payload[preferred] = _maybe_wrap_lua(selected_value)

            return json.dumps(payload, ensure_ascii=False)
        if force_json_wrap:
            keys = preferred_keys or []
            key = keys[0] if keys else "code"
            return json.dumps({key: _maybe_wrap_lua(cleaned)}, ensure_ascii=False)
        return cleaned

    if output_contract == "raw_lua":
        payload = maybe_parse_json(cleaned)
        if payload:
            for value in _collect_string_values(payload):
                canonical = _canonicalize_lua_wrapper(value.strip())
                match = LUA_WRAPPER_RE.match(canonical)
                if match:
                    return _normalize_lua_snippet(match.group(1).strip())
        return _normalize_lua_snippet(cleaned)

    return cleaned
