from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LUA_WRAPPER_RE = re.compile(r"^lua\{([\s\S]*)\}lua$")


@dataclass(frozen=True)
class OracleSpec:
    fixture: dict[str, Any]
    expected: Any
    expected_json_key: str | None = None


ORACLE_SPECS: dict[str, OracleSpec] = {
    "last_element": OracleSpec(
        fixture={"wf": {"vars": {"emails": ["user1@example.com", "user2@example.com", "user3@example.com"]}}},
        expected="user3@example.com",
        expected_json_key="lastEmail",
    ),
    "increment": OracleSpec(
        fixture={"wf": {"vars": {"try_count_n": 3}}},
        expected=4,
        expected_json_key="try_count_n",
    ),
    "keep_only_fields": OracleSpec(
        fixture={
            "wf": {
                "vars": {
                    "RESTbody": {
                        "result": [
                            {"ID": 123, "ENTITY_ID": 456, "CALL": "call_1", "EXTRA": "x"},
                            {"ID": 789, "ENTITY_ID": 101, "CALL": "call_2", "OTHER": "y"},
                        ]
                    }
                }
            }
        },
        expected=[
            {"ID": 123, "ENTITY_ID": 456, "CALL": "call_1"},
            {"ID": 789, "ENTITY_ID": 101, "CALL": "call_2"},
        ],
        expected_json_key="result",
    ),
    "datum_time_to_iso": OracleSpec(
        fixture={"wf": {"vars": {"json": {"IDOC": {"ZCDF_HEAD": {"DATUM": "20231015", "TIME": "153000"}}}}}},
        expected="2023-10-15T15:30:00.00000Z",
        expected_json_key="time",
    ),
    "iso_to_unix": OracleSpec(
        fixture={"wf": {"initVariables": {"recallTime": "2023-10-15T15:30:00+00:00"}}},
        expected=1697383800,
        expected_json_key="unix_time",
    ),
    "ensure_array": OracleSpec(
        fixture={
            "wf": {
                "vars": {
                    "json": {
                        "IDOC": {
                            "ZCDF_HEAD": {
                                "ZCDF_PACKAGES": [
                                    {"items": [{"sku": "A"}, {"sku": "B"}]},
                                    {"items": {"sku": "C"}},
                                ]
                            }
                        }
                    }
                }
            }
        },
        expected=[
            {"items": [{"sku": "A"}, {"sku": "B"}]},
            {"items": [{"sku": "C"}]},
        ],
        expected_json_key="packages",
    ),
    "filter_non_empty": OracleSpec(
        fixture={
            "wf": {
                "vars": {
                    "parsedCsv": [
                        {"SKU": "A001", "Discount": "10%", "Markdown": ""},
                        {"SKU": "A002", "Discount": "", "Markdown": "5%"},
                        {"SKU": "A003", "Discount": None, "Markdown": None},
                        {"SKU": "A004", "Discount": "", "Markdown": ""},
                    ]
                }
            }
        },
        expected=[
            {"SKU": "A001", "Discount": "10%", "Markdown": ""},
            {"SKU": "A002", "Discount": "", "Markdown": "5%"},
        ],
        expected_json_key="result",
    ),
    "multi_field_json": OracleSpec(
        fixture={"wf": {"initVariables": {"number": "5", "num": "5"}}},
        expected={"num": 5, "squared": 25},
    ),
}


def _lua_binary() -> str | None:
    found = shutil.which("lua5.4") or shutil.which("lua54") or shutil.which("lua")
    if found:
        return found
    for candidate in (
        r"C:\Program Files (x86)\Lua\5.1\lua.exe",
        r"C:\Program Files\Lua\5.4\lua.exe",
        r"C:\Program Files\Lua\5.1\lua.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _to_lua_literal(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "nil"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "{" + ", ".join(_to_lua_literal(item) for item in value) + "}"
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value.keys(), key=str):
            parts.append(f"[{json.dumps(str(key), ensure_ascii=False)}] = {_to_lua_literal(value[key])}")
        return "{" + ", ".join(parts) + "}"
    return "nil"


def _extract_wrappers(text: str) -> dict[str, str]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return {}
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    wrappers: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            continue
        match = LUA_WRAPPER_RE.match(value.strip())
        if match:
            wrappers[str(key)] = match.group(1).strip()
    return wrappers


def _build_harness(chunk: str, fixture: dict[str, Any]) -> str:
    wf_literal = _to_lua_literal(fixture.get("wf", {}))
    init_vars_literal = _to_lua_literal(fixture.get("wf", {}).get("initVariables", {}))
    return f"""
local wf = {wf_literal}
if not wf.vars then wf.vars = {{}} end
if not wf.initVariables then wf.initVariables = {init_vars_literal} end
local _utils = {{}}
_utils.array = {{}}
function _utils.array.new()
  return {{}}
end
function _utils.array.markAsArray(t)
  if type(t) ~= "table" then
    return t
  end
  return t
end
function _utils.array.push(t, v)
  table.insert(t, v)
  return t
end

local function __is_array(v)
  if type(v) ~= "table" then
    return false
  end
  local max_index = 0
  for k, _ in pairs(v) do
    if type(k) ~= "number" then
      return false
    end
    if k <= 0 or math.floor(k) ~= k then
      return false
    end
    if k > max_index then
      max_index = k
    end
  end
  for i = 1, max_index do
    if v[i] == nil then
      return false
    end
  end
  return true
end

local function __escape(s)
  s = string.gsub(s, "\\\\", "\\\\\\\\")
  s = string.gsub(s, '"', '\\\\"')
  s = string.gsub(s, "\\n", "\\\\n")
  s = string.gsub(s, "\\r", "\\\\r")
  s = string.gsub(s, "\\t", "\\\\t")
  return s
end

local function __encode(v)
  local t = type(v)
  if v == nil then
    return "null"
  end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then
      return "null"
    end
    return tostring(v)
  end
  if t == "boolean" then
    return v and "true" or "false"
  end
  if t == "string" then
    return '"' .. __escape(v) .. '"'
  end
  if t == "table" then
    if __is_array(v) then
      local parts = {{}}
      for i = 1, #v do
        parts[#parts + 1] = __encode(v[i])
      end
      return "[" .. table.concat(parts, ",") .. "]"
    end

    local key_strings = {{}}
    for k, _ in pairs(v) do
      key_strings[#key_strings + 1] = tostring(k)
    end
    table.sort(key_strings)
    local parts = {{}}
    for _, key in ipairs(key_strings) do
      parts[#parts + 1] = '"' .. __escape(key) .. '":' .. __encode(v[key])
    end
    return "{{" .. table.concat(parts, ",") .. "}}"
  end
  return "null"
end

local function __run()
{chunk}
end

local ok, result = pcall(__run)
if not ok then
  io.stderr:write(tostring(result))
  os.exit(3)
end

io.write(__encode(result))
""".strip()


def _execute_lua(lua_binary: str, chunk: str, fixture: dict[str, Any]) -> tuple[bool, Any, str]:
    script = _build_harness(chunk, fixture)
    try:
        proc = subprocess.run(
            [lua_binary, "-"],
            input=script,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False, None, ""

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:500]
        return False, None, stderr

    output = (proc.stdout or "").strip()
    if not output:
        return False, None, "empty output"

    try:
        return True, json.loads(output), ""
    except json.JSONDecodeError:
        return False, None, f"json decode error: {output[:200]}"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _pick_chunk(code: str, expected_json_key: str | None = None) -> str:
    wrappers = _extract_wrappers(code)
    if not wrappers:
        return code
    if expected_json_key and expected_json_key in wrappers:
        return wrappers[expected_json_key]
    return next(iter(wrappers.values()))


def execute_candidate(
    code: str,
    fixture: dict[str, Any],
    expected_json_key: str | None = None,
) -> tuple[bool, Any, str]:
    lua_binary = _lua_binary()
    if lua_binary is None:
        return False, None, "no lua binary found"

    wrappers = _extract_wrappers(code)
    if wrappers and isinstance(fixture.get("wf"), dict):
        wf_data = fixture.get("wf", {})
        has_vars = isinstance(wf_data.get("vars"), dict)
        has_init = isinstance(wf_data.get("initVariables"), dict)

        if has_init and len(wrappers) > 1:
            actual: dict[str, Any] = {}
            for key, chunk in wrappers.items():
                ok, value, error = _execute_lua(lua_binary, chunk, fixture)
                if not ok:
                    return False, None, f"wrapper {key} failed: {error}"
                actual[key] = value
            return True, _normalize(actual), ""

    chunk = _pick_chunk(code, expected_json_key)
    ok, value, error = _execute_lua(lua_binary, chunk, fixture)
    if ok:
        value = _normalize(value)
    return ok, value, error


def runtime_oracle_pass(
    code: str,
    fixture: dict[str, Any],
    expected_output: Any,
    expected_json_key: str | None = None,
) -> tuple[bool | None, str]:
    lua_binary = _lua_binary()
    if lua_binary is None:
        return None, "no lua binary"

    if not fixture or expected_output is None:
        return None, "no fixture or expected"

    ok, actual, error = execute_candidate(code, fixture, expected_json_key)
    if not ok:
        return False, f"execution failed: {error}"

    expected = _normalize(expected_output)
    if actual == expected:
        return True, ""

    return False, f"expected {json.dumps(expected, ensure_ascii=False)[:300]}, got {json.dumps(actual, ensure_ascii=False)[:300]}"


def oracle_semantic_pass(task_type: str, code: str) -> bool | None:
    spec = ORACLE_SPECS.get(task_type)
    if spec is None:
        return None

    lua_binary = _lua_binary()
    if lua_binary is None:
        return None

    wrappers = _extract_wrappers(code)
    expected = _normalize(spec.expected)

    if task_type == "multi_field_json":
        if wrappers:
            actual: dict[str, Any] = {}
            for key in ("num", "squared"):
                chunk = wrappers.get(key)
                if not chunk:
                    return False
                ok, value, _ = _execute_lua(lua_binary, chunk, spec.fixture)
                if not ok:
                    return False
                actual[key] = value
            return _normalize(actual) == expected

        ok, value, _ = _execute_lua(lua_binary, code, spec.fixture)
        if not ok:
            return False
        return _normalize(value) == expected

    chunk_to_run = _pick_chunk(code, spec.expected_json_key)

    ok, value, _ = _execute_lua(lua_binary, chunk_to_run, spec.fixture)
    if not ok:
        return False

    return _normalize(value) == expected
