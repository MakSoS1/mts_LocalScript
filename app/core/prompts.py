from __future__ import annotations

from app.core.planner import TaskPlan
from app.core.retrieval import RetrievalContext


SYSTEM_PROMPT = """
You generate only valid Lua code for a constrained LowCode environment.
Rules:
1. Never use JsonPath.
2. Use direct field access via wf.vars and wf.initVariables where relevant.
3. Return only code (or valid JSON if requested), without markdown fences and prose.
4. If JSON output with Lua snippets is required, use exact wrapper format: lua{...}lua.
5. Do not invent helper APIs except _utils.array.new and _utils.array.markAsArray.
6. Produce the minimal correct solution.
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
Instruction: {mode_instruction}
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
