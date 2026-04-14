from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field


TASK_TYPES = {
    "last_element",
    "increment",
    "keep_only_fields",
    "datum_time_to_iso",
    "iso_to_unix",
    "ensure_array",
    "filter_non_empty",
    "multi_field_json",
    "generic",
}

OPERATION_TYPES = {
    "get_element",
    "increment",
    "keep_only_fields",
    "convert_time",
    "filter",
    "normalize_array",
    "conditional_return",
    "aggregate",
    "build_string",
    "multi_field",
    "generic",
}

TASK_TYPE_TO_OPERATION = {
    "last_element": "get_element",
    "increment": "increment",
    "keep_only_fields": "keep_only_fields",
    "datum_time_to_iso": "convert_time",
    "iso_to_unix": "convert_time",
    "ensure_array": "normalize_array",
    "filter_non_empty": "filter",
    "multi_field_json": "multi_field",
    "generic": "generic",
}


@dataclass(slots=True)
class TaskPlan:
    task_type: str
    output_contract: str
    target_paths: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    assumptions: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    confidence: float = 0.5
    operation_type: str = "generic"
    source_paths: list[str] = field(default_factory=list)
    fields_to_keep: list[str] = field(default_factory=list)
    needs_array_normalization: bool = False
    time_format_conversion: str = ""
    edge_cases: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    def to_prompt_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


PATH_RE = re.compile(r"wf\.(?:vars|initVariables)\.[A-Za-z0-9_.]+")
TRAILING_PATH_PUNCTUATION = ".,;:!?)]}\"'"
OUTPUT_KEY_PATTERNS = [
    re.compile(
        r"верни\s+(?:результат|значение)\s+в\s+(?:переменн\w+\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    ),
    re.compile(r"верни\s+результат\s+в\s+(?:переменн\w+\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"верни\s+в\s+(?:переменн\w+\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"верни\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", re.IGNORECASE),
    re.compile(
        r"(?:определи|собери|посчитай|рассчитай|вычисли)\s+(?:значение\s+|флаг\s+|поле\s+|объект\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    ),
    re.compile(r"return\s+(?:the\s+result\s+)?(?:as|in)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"return\s+(?:the\s+)?value\s+(?:as|in)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"return\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:as|object)", re.IGNORECASE),
    re.compile(r"return\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", re.IGNORECASE),
    re.compile(
        r"(?:determine|build|calculate|compute)\s+(?:the\s+)?(?:value\s+|flag\s+|field\s+|object\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    ),
]


def _extract_paths(prompt: str) -> list[str]:
    found = PATH_RE.findall(prompt)
    deduped: list[str] = []
    for item in found:
        normalized = item.rstrip(TRAILING_PATH_PUNCTUATION)
        if not normalized:
            continue
        if normalized.endswith("."):
            normalized = normalized.rstrip(".")
        if not normalized:
            continue
        item = normalized
        if item not in deduped:
            deduped.append(item)
    return deduped


def _detect_task_type(prompt: str) -> tuple[str, str, float]:
    lowered = prompt.lower()
    if ("послед" in lowered or "last" in lowered) and "email" in lowered:
        return "last_element", "get_element", 0.95
    if "try_count" in lowered or "инкрем" in lowered or "увеличивай" in lowered:
        return "increment", "increment", 0.95
    if ("id" in lowered and "entity_id" in lowered and "call" in lowered) or "keep only" in lowered:
        return "keep_only_fields", "keep_only_fields", 0.9
    if ("datum" in lowered and "time" in lowered and "iso" in lowered) or "yyyymmdd" in lowered:
        return "datum_time_to_iso", "convert_time", 0.95
    if "recalltime" in lowered and "unix" in lowered:
        return "iso_to_unix", "convert_time", 0.95
    if "zcdf_packages" in lowered and ("items" in lowered or "array" in lowered or "массив" in lowered):
        return "ensure_array", "normalize_array", 0.9
    if ("discount" in lowered or "markdown" in lowered) and ("filter" in lowered or "отфильтр" in lowered):
        return "filter_non_empty", "filter", 0.9
    if "square" in lowered or "квадрат" in lowered or "squared" in lowered:
        return "multi_field_json", "multi_field", 0.85
    return "generic", "generic", 0.4


def _infer_output_contract(prompt: str, task_type: str) -> str:
    lowered = prompt.lower()
    prompt_without_paths = PATH_RE.sub(" ", prompt)
    lowered_without_paths = prompt_without_paths.lower()

    explicit_raw = any(token in lowered for token in ("raw lua", "только lua", "только код", "без json"))
    explicit_json = any(
        token in lowered_without_paths
        for token in (
            "json",
            "lua{",
            "оберт",
            "wrapper",
            "json object",
            "верни json",
            "return json",
        )
    )
    has_explicit_wf_path = bool(_extract_paths(prompt))

    if explicit_raw:
        return "raw_lua"
    if explicit_json:
        return "json_with_lua_wrappers"
    if has_explicit_wf_path:
        return "raw_lua"
    return "json_with_lua_wrappers"


def _default_output_keys(task_type: str) -> list[str]:
    by_type = {
        "last_element": ["lastEmail"],
        "increment": ["try_count_n"],
        "keep_only_fields": ["result"],
        "datum_time_to_iso": ["time"],
        "iso_to_unix": ["unix_time"],
        "ensure_array": ["packages"],
        "filter_non_empty": ["result"],
        "multi_field_json": ["num", "squared"],
    }
    return by_type.get(task_type, [])


def _extract_output_keys(prompt: str) -> list[str]:
    keys: list[str] = []
    for pattern in OUTPUT_KEY_PATTERNS:
        for match in pattern.findall(prompt):
            key = str(match).strip()
            if not key:
                continue
            if key not in keys:
                keys.append(key)
    return keys


def _infer_operation_type(prompt: str, task_type: str) -> str:
    base = TASK_TYPE_TO_OPERATION.get(task_type, "generic")
    if base != "generic":
        return base
    lowered = prompt.lower()
    if any(tok in lowered for tok in ("если", "if ", "услов", "conditional")):
        return "conditional_return"
    if any(tok in lowered for tok in ("сумм", "sum", "count", "количеств", "aggregate", "агрег")):
        return "aggregate"
    if any(tok in lowered for tok in ("собери", "build", "конкат", "concat", "строк", "string build")):
        return "build_string"
    return "generic"


FIELDS_RE = re.compile(r"\b([A-Z_][A-Z0-9_]*)\b")


def _infer_fields_to_keep(prompt: str, task_type: str) -> list[str]:
    if task_type != "keep_only_fields":
        return []
    found = FIELDS_RE.findall(prompt)
    return list(dict.fromkeys(found))


def _infer_edge_cases(prompt: str, task_type: str) -> list[str]:
    cases: list[str] = []
    lowered = prompt.lower()
    if any(tok in lowered for tok in ("nil", "null", "отсутств", "может быть пуст", "может не сущ")):
        cases.append("nil_guard")
    elif task_type in ("increment", "keep_only_fields", "convert_time", "ensure_array", "filter_non_empty"):
        cases.append("nil_guard")
    if task_type in ("ensure_array", "filter_non_empty") or "массив" in lowered or "array" in lowered:
        if "empty_array" not in cases:
            cases.append("empty_array")
    if task_type in ("datum_time_to_iso", "iso_to_unix"):
        cases.append("string_number")
    return cases


def _infer_acceptance_criteria(plan: TaskPlan) -> list[str]:
    criteria: list[str] = []
    if plan.output_contract == "json_with_lua_wrappers":
        criteria.append("Output must be JSON with lua{...}lua wrappers")
    elif plan.output_contract == "raw_lua":
        criteria.append("Output must be raw Lua code")
    for key in plan.output_keys:
        criteria.append(f"JSON must contain key '{key}'")
    if plan.edge_cases:
        for ec in plan.edge_cases:
            if ec == "nil_guard":
                criteria.append("Must guard against nil input")
            elif ec == "empty_array":
                criteria.append("Must handle empty arrays")
            elif ec == "string_number":
                criteria.append("Must coerce string-number values")
    if plan.operation_type == "increment":
        criteria.append("Must increment numeric value by 1")
    elif plan.operation_type == "keep_only_fields":
        criteria.append("Must keep only specified fields")
    elif plan.operation_type == "convert_time":
        criteria.append("Must convert time format correctly")
    elif plan.operation_type == "normalize_array":
        criteria.append("Must normalize to array with markAsArray")
    elif plan.operation_type == "filter":
        criteria.append("Must filter out empty/null items")
    return criteria


def plan_task(prompt: str) -> TaskPlan:
    task_type, operation_type, confidence = _detect_task_type(prompt)
    if task_type not in TASK_TYPES:
        task_type = "generic"
        operation_type = "generic"
    output_contract = _infer_output_contract(prompt, task_type)
    target_paths = _extract_paths(prompt)
    assumptions: list[str] = []

    if not target_paths:
        assumptions.append("Use canonical domain paths from retrieved examples.")
    if task_type == "generic":
        assumptions.append("Use minimal valid Lua and avoid non-domain helpers.")

    needs_clarification = task_type == "generic" and confidence < 0.5 and not target_paths
    output_keys = _extract_output_keys(prompt) or _default_output_keys(task_type)

    inferred_op = _infer_operation_type(prompt, task_type)
    if inferred_op != "generic":
        operation_type = inferred_op
    if operation_type not in OPERATION_TYPES:
        operation_type = "generic"

    fields_to_keep = _infer_fields_to_keep(prompt, task_type)
    needs_array_normalization = task_type == "ensure_array"
    time_format_conversion = ""
    if task_type == "datum_time_to_iso":
        time_format_conversion = "datum_to_iso"
    elif task_type == "iso_to_unix":
        time_format_conversion = "iso_to_unix"

    plan = TaskPlan(
        task_type=task_type,
        output_contract=output_contract,
        target_paths=target_paths,
        needs_clarification=needs_clarification,
        assumptions=assumptions,
        output_keys=output_keys,
        confidence=confidence,
        operation_type=operation_type,
        source_paths=list(target_paths),
        fields_to_keep=fields_to_keep,
        needs_array_normalization=needs_array_normalization,
        time_format_conversion=time_format_conversion,
    )
    plan.edge_cases = _infer_edge_cases(prompt, task_type)
    plan.acceptance_criteria = _infer_acceptance_criteria(plan)
    return plan
