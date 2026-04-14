from __future__ import annotations

import json

from app.core.planner import TaskPlan
from app.core.retrieval import RetrievalContext


CLARIFICATION_SYSTEM_PROMPT = """
You analyze Lua LowCode coding tasks and identify what is unclear or ambiguous.
You must ask a clarifying question in Russian and provide 2-4 assumptions the user can choose from.

Common ambiguities to check:
- Output format: raw Lua code or JSON with lua{...}lua wrappers
- What to return: a list of values, a count/number, a single value, a boolean flag
- Where to store the result: which wf.vars.X or wf.initVariables.Y variable
- Data source: where the input data comes from (if not specified)
- Edge cases: handling nil, empty arrays, invalid input
- Algorithm details: which algorithm or approach to use when multiple exist

Response format (STRICTLY follow this):
QUESTION: <your clarifying question in Russian, one or two sentences>
ASSUMPTION: <assumption 1 - MUST end with either ", raw Lua" or ", JSON wrappers" to indicate format>
ASSUMPTION: <assumption 2>
ASSUMPTION: <assumption 3 (optional)>
ASSUMPTION: <assumption 4 (optional)>

Example 1:
Task: "напиши lua код который найдет все простые числа до 1000"
QUESTION: Что именно нужно вернуть — список всех простых чисел или их количество? В каком формате вывести результат?
ASSUMPTION: Список простых чисел, raw Lua
ASSUMPTION: Список простых чисел, JSON wrappers
ASSUMPTION: Количество простых чисел, raw Lua
ASSUMPTION: Количество простых чисел, JSON wrappers

Example 2:
Task: "отфильтруй пустые элементы из массива wf.vars.deals"
QUESTION: Нужно ли сохранять результат в конкретную переменную? Какой формат вывода preferred?
ASSUMPTION: Сохранить в wf.vars.filtered_deals, raw Lua
ASSUMPTION: Вернуть отфильтрованный массив, JSON wrappers
""".strip()


SYSTEM_PROMPT = """
You generate only valid Lua code for a constrained LowCode environment.
Rules:
1. Never use JsonPath.
2. Use ONLY the paths mentioned in the task (wf.vars.X, wf.initVariables.Y). Do NOT invent paths like RESTbody.result unless explicitly stated in the task.
3. Return only code (or valid JSON if requested), without markdown fences and prose.
4. If JSON output with Lua snippets is required, use exact wrapper format: lua{...}lua.
5. Do not invent helper APIs except _utils.array.new and _utils.array.markAsArray.
6. Produce the minimal correct solution.
7. Lua snippets must contain explicit `return` of the final result.
8. NEVER use nested wrappers like lua{lua{...}lua}lua. Each lua{...}lua must appear exactly once per JSON key value and must not contain another lua{ or }lua inside.
9. In lua{...}lua wrappers, write plain Lua code with return statement. Do NOT wrap inner values in another lua{...}lua.
10. Always use tonumber() for numeric comparisons and arithmetic on wf.vars values.
11. Always guard against nil with `or 0`, `or ""`, `or {}` as appropriate.
""".strip()

IR_SYSTEM_PROMPT = """
You produce a JSON intermediate representation (IR) for a Lua LowCode task.
Output ONLY a single JSON object with these fields:
- "read_from": exact dot-path where input data lives (e.g. "wf.vars.try_count_n" or "wf.vars.deals"). Use ONLY paths mentioned in the task. Do NOT invent paths like RESTbody.result unless explicitly stated.
- "operation": one of get_element, increment, keep_only_fields, convert_time, filter, normalize_array, conditional_return, aggregate, build_string, multi_field, generic
- "fields": array of field names to keep/remove (if applicable, else [])
- "return_as": "json_with_lua_wrappers" or "raw_lua"
- "json_key": the output key name for JSON wrapper (if return_as is json_with_lua_wrappers)
- "edge_cases": array of edge case names like nil_guard, empty_array, string_number, missing_field
- "mutate_in_place": true or false
Rules:
1. read_from MUST use paths from the task text. If the task says "wf.vars.deals", use "wf.vars.deals", NOT "wf.vars.RESTbody.result".
2. Do NOT add intermediate path segments not present in the task.
3. Output ONLY valid JSON, no markdown fences, no prose.
""".strip()


def infer_output_contract(task: str) -> str:
    lowered = task.lower()
    if any(token in lowered for token in ("raw lua", "только lua", "только код", "без json")):
        return "raw_lua"
    if any(token in lowered for token in ("json", "lua{", "оберт", "wrapper")):
        return "json_with_lua_wrappers"
    if "wf.vars" in lowered or "wf.initvariables" in lowered:
        return "raw_lua"
    return "json_with_lua_wrappers"


def _format_examples(context: RetrievalContext) -> str:
    if not context.examples:
        return "No local examples matched."

    blocks: list[str] = []
    for ex in context.examples:
        minimal_lua = "\n".join(ex.expected_lua.splitlines()[:8]).strip()
        blocks.append(
            "\n".join(
                [
                    f"Example ID: {ex.id}",
                    f"Task Archetype: {ex.archetype}",
                    f"Critical Pattern: {ex.critical_pattern}",
                    f"Output mode: {ex.output_mode}",
                    "Minimal good example:",
                    minimal_lua,
                ]
            )
        )
    return "\n\n".join(blocks)


def build_generation_messages(
    task: str,
    context: RetrievalContext,
    plan: TaskPlan,
    request_mode: str,
    output_contract: str,
    candidate_strategy: str | None = None,
) -> list[dict]:
    mode_instruction = {
        "direct_generation": "Generate directly.",
        "clarify_then_generate": "If ambiguous, choose conservative assumptions and still return code.",
        "generate_then_repair": "Prefer robust code style to maximize validator pass.",
    }.get(request_mode, "Generate directly.")

    user_prompt = f"""
Task:
{task}

Mode: {request_mode}
Output contract: {output_contract}
Expected output key(s): {plan.output_keys}
Instruction: {mode_instruction}
Candidate strategy: {candidate_strategy or 'Default balanced solution.'}
External API contract reminder: input prompt -> output code.

Planner output (JSON):
{plan.to_prompt_json()}

Local Rules:
{context.rules or 'N/A'}

Anti-patterns:
{context.anti_patterns or 'N/A'}

Top Examples:
{_format_examples(context)}

Return only final code.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_repair_messages(
    task: str,
    previous_code: str,
    validator_errors: list[str],
    context: RetrievalContext,
    plan: TaskPlan,
    output_contract: str,
) -> list[dict]:
    error_lines = "\n".join(f"- {err}" for err in validator_errors)

    user_prompt = f"""
Repair this code.
Task:
{task}

Previous code:
{previous_code}

Validator errors:
{error_lines}

Expected output contract:
{output_contract}
Expected output key(s):
{plan.output_keys}

Planner output (JSON):
{plan.to_prompt_json()}

Repair hints:
{context.repair_hints or 'N/A'}

Rules:
{context.rules or 'N/A'}

Return only corrected code.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_feedback_repair_messages(
    prompt: str,
    previous_code: str,
    feedback: str,
    context: RetrievalContext,
    plan: TaskPlan,
    output_contract: str,
) -> list[dict]:
    user_prompt = f"""
Apply minimal changes to the previous code according to user feedback.
Task:
{prompt}

User feedback:
{feedback}

Previous code:
{previous_code}

Expected output contract:
{output_contract}
Expected output key(s):
{plan.output_keys}

Planner output (JSON):
{plan.to_prompt_json()}

Rules:
{context.rules or 'N/A'}

Anti-patterns:
{context.anti_patterns or 'N/A'}

Requirements:
1. Keep unchanged logic intact.
2. Modify only what is required by feedback.
3. Return only final code.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_ir_generation_messages(
    task: str,
    context: RetrievalContext,
    plan: TaskPlan,
    output_contract: str,
) -> list[dict]:
    user_prompt = f"""
Produce the JSON-IR for the following task.
Task:
{task}

Output contract: {output_contract}
Expected output key(s): {plan.output_keys}

Planner output (JSON):
{plan.to_prompt_json()}

Operation type: {plan.operation_type}
Source paths: {plan.source_paths}
Fields to keep: {plan.fields_to_keep}
Edge cases: {plan.edge_cases}
Time format conversion: {plan.time_format_conversion or 'none'}
Needs array normalization: {plan.needs_array_normalization}

Top Examples:
{_format_examples(context)}

Output ONLY the JSON-IR object, nothing else.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_clarification_messages(
    task: str,
    plan: TaskPlan,
) -> list[dict]:
    user_prompt = f"""
Task:
{task}

Planner analysis:
- Task type: {plan.task_type}
- Operation type: {plan.operation_type}
- Output contract (inferred): {plan.output_contract}
- Target paths: {plan.target_paths or 'not specified'}
- Output keys: {plan.output_keys or 'not specified'}
- Edge cases: {plan.edge_cases or 'none detected'}
- Confidence: {plan.confidence}
- Assumptions already made: {plan.assumptions}

Identify what is ambiguous or unclear about this task and generate a clarification question with assumptions.
Remember: each ASSUMPTION line MUST end with either ", raw Lua" or ", JSON wrappers".
""".strip()

    return [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_ir_to_lua_messages(
    ir_json: str,
    context: RetrievalContext,
    plan: TaskPlan,
    output_contract: str,
    *,
    original_task: str = "",
) -> list[dict]:
    task_section = f"\nOriginal task:\n{original_task}\n" if original_task else ""
    user_prompt = f"""
Generate Lua code from the following IR specification.
{task_section}
IR:
{ir_json}

Output contract: {output_contract}
Expected output key(s): {plan.output_keys}

Planner output (JSON):
{plan.to_prompt_json()}

Local Rules:
{context.rules or 'N/A'}

Anti-patterns:
{context.anti_patterns or 'N/A'}

Top Examples:
{_format_examples(context)}

Requirements:
1. Implement exactly what the IR specifies.
2. Handle all edge cases listed in the IR.
3. Respect the return_as format (json_with_lua_wrappers or raw_lua).
4. Never nest lua{{...}}lua wrappers inside other lua{{...}}lua wrappers.
5. Return only final code.
""".strip()

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
