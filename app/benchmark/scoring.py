from __future__ import annotations

import json

from app.benchmark.oracle import oracle_semantic_pass, runtime_oracle_pass
from app.core.orchestrator import GenerationResult


def _contains_all(code: str, needles: list[str]) -> bool:
    lowered = code.lower()
    return all(needle.lower() in lowered for needle in needles)


def _contains_any(code: str, needles: list[str]) -> bool:
    if not needles:
        return True
    lowered = code.lower()
    return any(needle.lower() in lowered for needle in needles)


def _contains_none(code: str, needles: list[str]) -> bool:
    lowered = code.lower()
    return all(needle.lower() not in lowered for needle in needles)


def _task_type_from_case(case_id: str) -> str:
    case_id = case_id.lower()
    if case_id in {"last_array_element", "aug_last_email_en"}:
        return "last_element"
    if case_id in {"increment_try_counter", "aug_counter_ru"}:
        return "increment"
    if case_id in {"cleanup_rest_result_keys", "aug_cleanup_en"}:
        return "keep_only_fields"
    if case_id in {"datum_time_to_iso8601", "aug_iso_ru"}:
        return "datum_time_to_iso"
    if case_id in {"iso8601_to_unix", "aug_unix_en"}:
        return "iso_to_unix"
    if case_id in {"ensure_items_are_arrays", "aug_array_norm_en"}:
        return "ensure_array"
    if case_id in {"filter_discount_or_markdown", "aug_filter_ru"}:
        return "filter_non_empty"
    if case_id in {"extend_existing_code_square_number", "aug_square_ru"}:
        return "multi_field_json"
    return "generic"


def _semantic_task_pass(task_type: str, code: str) -> bool:
    oracle_result = oracle_semantic_pass(task_type, code)
    if oracle_result is not None:
        return oracle_result

    lowered = code.lower()
    by_task = {
        "last_element": ["wf.vars.emails"],
        "increment": ["wf.vars.try_count_n"],
        "keep_only_fields": ["wf.vars.restbody.result"],
        "datum_time_to_iso": ["datum", "time"],
        "iso_to_unix": ["recalltime"],
        "ensure_array": ["zcdf_packages"],
        "filter_non_empty": ["parsedcsv"],
        "multi_field_json": ["squared"],
    }
    needles = by_task.get(task_type, [])
    if not needles:
        return True
    return all(needle in lowered for needle in needles)


def semantic_pass(case: dict, code: str) -> tuple[bool, str]:
    wf_fixture = case.get("wf_fixture")
    expected_runtime_output = case.get("expected_runtime_output")

    if wf_fixture and expected_runtime_output is not None:
        expected_json_key = case.get("expected_json_key")
        oracle_ok, oracle_detail = runtime_oracle_pass(
            code, wf_fixture, expected_runtime_output, expected_json_key
        )
        if oracle_ok is not None:
            return oracle_ok, f"runtime_oracle: {oracle_detail}" if not oracle_ok else "runtime_oracle: pass"

    task_type = str(case.get("task_type", "")).strip().lower() or _task_type_from_case(str(case.get("id", "")))
    if task_type != "generic":
        return _semantic_task_pass(task_type, code), f"task_type_oracle: {task_type}"

    must_have = [str(x) for x in case.get("expected_contains", [])]
    any_of = [str(x) for x in case.get("expected_any_contains", [])]
    must_not = [str(x) for x in case.get("expected_not_contains", [])]
    if must_have and not _contains_all(code, must_have):
        return False, "expected_contains mismatch"
    if any_of and not _contains_any(code, any_of):
        return False, "expected_any_contains mismatch"
    if must_not and not _contains_none(code, must_not):
        return False, "expected_not_contains violation"
    return True, ""


def latency_score(latency_ms: float) -> float:
    return max(0.0, 1.0 - latency_ms / 8000.0)


def format_pass(case: dict, result: GenerationResult) -> bool:
    base_ok = result.validation.output.ok and result.validation.contract.ok
    if not base_ok:
        return False

    expected_mode = str(case.get("expected_mode", "")).strip().lower()
    is_json = result.code.strip().startswith("{")
    if expected_mode == "json_with_lua_wrappers":
        return is_json
    if expected_mode == "raw_lua":
        return not is_json
    return True


def _hard_gate_pass(case: dict, result: GenerationResult) -> bool:
    v = result.validation
    return v.output.ok and v.contract.ok and v.domain.ok and v.syntax.ok


def score_case(case: dict, result: GenerationResult, latency_ms: float) -> dict:
    semantic, semantic_detail = semantic_pass(case, result.code)
    domain = result.validation.domain.ok
    syntax = result.validation.syntax.ok
    fmt = format_pass(case, result)
    latency = latency_score(latency_ms)

    if not _hard_gate_pass(case, result):
        return {
            "semantic_pass": bool(semantic),
            "domain_pass": bool(domain),
            "syntax_pass": bool(syntax),
            "format_pass": bool(fmt),
            "latency_score": round(latency, 4),
            "hard_gate": False,
            "total_score": 0.0,
            "semantic_detail": semantic_detail,
        }

    total = (
        55.0 * (1.0 if semantic else 0.0)
        + 10.0 * (1.0 if domain else 0.0)
        + 15.0 * (1.0 if syntax else 0.0)
        + 10.0 * (1.0 if fmt else 0.0)
        + 10.0 * latency
    )

    return {
        "semantic_pass": bool(semantic),
        "domain_pass": bool(domain),
        "syntax_pass": bool(syntax),
        "format_pass": bool(fmt),
        "latency_score": round(latency, 4),
        "hard_gate": True,
        "total_score": round(total, 2),
        "semantic_detail": semantic_detail,
    }
