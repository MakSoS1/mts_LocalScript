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


@dataclass(slots=True)
class TaskPlan:
    task_type: str
    output_contract: str
    target_paths: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    assumptions: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    confidence: float = 0.5

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


def _detect_task_type(prompt: str) -> tuple[str, float]:
    lowered = prompt.lower()
    if ("послед" in lowered or "last" in lowered) and "email" in lowered:
        return "last_element", 0.95
    if "try_count" in lowered or "инкрем" in lowered or "увеличивай" in lowered:
        return "increment", 0.95
    if ("id" in lowered and "entity_id" in lowered and "call" in lowered) or "keep only" in lowered:
        return "keep_only_fields", 0.9
    if ("datum" in lowered and "time" in lowered and "iso" in lowered) or "yyyymmdd" in lowered:
        return "datum_time_to_iso", 0.95
    if "recalltime" in lowered and "unix" in lowered:
        return "iso_to_unix", 0.95
    if "zcdf_packages" in lowered and ("items" in lowered or "array" in lowered or "массив" in lowered):
        return "ensure_array", 0.9
    if ("discount" in lowered or "markdown" in lowered) and ("filter" in lowered or "отфильтр" in lowered):
        return "filter_non_empty", 0.9
    if "square" in lowered or "квадрат" in lowered or "squared" in lowered:
        return "multi_field_json", 0.85
    return "generic", 0.4


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


def plan_task(prompt: str) -> TaskPlan:
    task_type, confidence = _detect_task_type(prompt)
    if task_type not in TASK_TYPES:
        task_type = "generic"
    output_contract = _infer_output_contract(prompt, task_type)
    target_paths = _extract_paths(prompt)
    assumptions: list[str] = []

    if not target_paths:
        assumptions.append("Use canonical domain paths from retrieved examples.")
    if task_type == "generic":
        assumptions.append("Use minimal valid Lua and avoid non-domain helpers.")

    needs_clarification = task_type == "generic" and confidence < 0.5 and not target_paths
    output_keys = _extract_output_keys(prompt) or _default_output_keys(task_type)

    return TaskPlan(
        task_type=task_type,
        output_contract=output_contract,
        target_paths=target_paths,
        needs_clarification=needs_clarification,
        assumptions=assumptions,
        output_keys=output_keys,
        confidence=confidence,
    )
