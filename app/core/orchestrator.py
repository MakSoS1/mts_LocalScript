from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.core.model_client import OllamaClient
from app.core.planner import TaskPlan, plan_task
from app.core.prompts import (
    build_feedback_repair_messages,
    build_generation_messages,
    build_repair_messages,
)
from app.core.retrieval import LocalRetriever
from app.utils.extract_code import normalize_output_contract
from app.utils.logging import get_logger
from app.validators.lua_quality_validator import analyze_lua_tools, format_lua_code
from app.validators.pipeline import run_all_validators
from app.validators.types import ValidationBundle


LOGGER = get_logger(__name__)


@dataclass(slots=True)
class GenerationResult:
    code: str
    model: str
    request_mode: str
    benchmark_mode: str
    raw_output: str
    repaired_output: str | None
    validation: ValidationBundle
    used_repair: bool
    plan: TaskPlan


@dataclass(slots=True)
class AgentIterationResult:
    status: str
    code: str | None
    model: str
    request_mode: str
    benchmark_mode: str
    used_repair: bool
    validation: ValidationBundle | None
    question: str | None = None
    acceptable_assumptions: list[str] | None = None
    assumptions: list[str] | None = None
    output_contract: str | None = None


@dataclass(slots=True)
class CandidateAssessment:
    raw_output: str
    code: str
    validation: ValidationBundle
    lua_quality: dict[str, Any]
    strategy: str


class Orchestrator:
    def __init__(self, settings: Settings, client: OllamaClient, retriever: LocalRetriever):
        self.settings = settings
        self.client = client
        self.retriever = retriever

    def classify_request_mode(self, prompt: str, override: str | None = None) -> str:
        if override in {"direct_generation", "clarify_then_generate", "generate_then_repair"}:
            return override

        lowered = prompt.lower()
        if any(token in lowered for token in ("уточни", "clarify", "неоднознач", "assumption")):
            return "clarify_then_generate"
        if len(prompt) > 280:
            return "generate_then_repair"
        return "direct_generation"

    def clarification_assumptions(self, plan: TaskPlan) -> list[str]:
        assumptions: list[str] = []
        if plan.output_contract == "json_with_lua_wrappers":
            assumptions.append("json_with_lua_wrappers")
            assumptions.append("raw_lua")
        else:
            assumptions.append("raw_lua")
            assumptions.append("json_with_lua_wrappers")
        return assumptions

    def clarification_question(self, plan: TaskPlan) -> str:
        if not plan.target_paths:
            return (
                "Нужен формат ответа: raw Lua или JSON с lua{...}lua wrappers? "
                "Также уточните целевой путь wf.vars/wf.initVariables, если он обязателен."
            )
        return "Нужен формат ответа: raw Lua или JSON с lua{...}lua wrappers?"

    def resolve_benchmark_mode(self, mode: str | None) -> str:
        if not mode:
            return "R3"
        upper = mode.upper()
        if upper in {"R0", "R1", "R2", "R3"}:
            return upper
        return "R3"

    def _mode_settings(self, benchmark_mode: str) -> tuple[bool, bool, bool]:
        if benchmark_mode == "R0":
            return False, False, False
        if benchmark_mode == "R1":
            return True, False, False
        if benchmark_mode == "R2":
            return True, True, False
        return True, True, True

    def _candidate_strategies(self) -> list[str]:
        base = [
            "Prefer the shortest correct solution that still respects the contract.",
            "Prefer a defensive implementation with explicit locals, tonumber/tostring guards, and clear normalization steps.",
            "Prefer a readable step-by-step implementation with intermediate variables and conservative branching.",
        ]
        count = max(1, self.settings.generation_candidate_count)
        return base[:count]

    def _chat_options(self, *, temperature: float, top_p: float = 0.9) -> dict[str, Any]:
        return {
            "num_ctx": 4096,
            "num_predict": 256,
            "num_batch": self.settings.ollama_num_batch,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": 40,
            "repeat_penalty": 1.05,
        }

    def _assess_candidate(
        self,
        *,
        raw_output: str,
        prompt: str,
        output_contract: str,
        plan: TaskPlan,
        strategy: str,
    ) -> CandidateAssessment:
        code = normalize_output_contract(
            raw_output,
            output_contract,
            preferred_keys=plan.output_keys,
            force_json_wrap=(output_contract == "json_with_lua_wrappers"),
        )
        code = format_lua_code(code, stylua_binary=self.settings.stylua_binary)
        validation = run_all_validators(
            code,
            prompt,
            self.settings.luac_binary,
            expected_contract=output_contract,
            syntax_require_luac=self.settings.syntax_require_luac,
            task_type=plan.task_type,
        )
        lua_quality = analyze_lua_tools(
            code,
            luac_binary=self.settings.luac_binary,
            luacheck_binary=self.settings.luacheck_binary,
            stylua_binary=self.settings.stylua_binary,
        )
        return CandidateAssessment(
            raw_output=raw_output,
            code=code,
            validation=validation,
            lua_quality=lua_quality,
            strategy=strategy,
        )

    def _candidate_issue_strings(self, candidate: CandidateAssessment) -> list[str]:
        issues = [
            f"{issue.validator}:{issue.code}:{issue.hint}"
            for issue in candidate.validation.all_issues
        ]
        for chunk in candidate.lua_quality["chunks"]:
            label = chunk["label"]
            for tool_name in ("syntax", "lint", "format"):
                tool = chunk[tool_name]
                if tool["status"] != "failed":
                    continue
                details = tool.get("details") or f"{tool_name} failed"
                issues.append(f"{tool_name}:{label}:{details}")
        return issues

    def _candidate_rank(self, candidate: CandidateAssessment) -> tuple[int, ...]:
        task_ok = True if candidate.validation.task is None else candidate.validation.task.ok
        quality = candidate.lua_quality["summary"]
        failed_tools = sum(
            1 for key in ("syntax_pass", "lint_pass", "format_pass") if quality.get(key) is False
        )
        return (
            1 if candidate.validation.ok else 0,
            1 if candidate.validation.contract.ok else 0,
            1 if candidate.validation.output.ok else 0,
            1 if candidate.validation.syntax.ok else 0,
            1 if candidate.validation.domain.ok else 0,
            1 if task_ok else 0,
            1 if quality.get("quality_gate_pass") is True else 0,
            1 if quality.get("syntax_pass") is True else 0,
            1 if quality.get("lint_pass") is True else 0,
            1 if quality.get("format_pass") is True else 0,
            -failed_tools,
            -len(candidate.validation.all_issues),
            -len(candidate.code),
        )

    def _pick_best_candidate(self, candidates: list[CandidateAssessment]) -> CandidateAssessment:
        return max(candidates, key=self._candidate_rank)

    def _candidate_is_acceptable(self, candidate: CandidateAssessment) -> bool:
        quality_gate = candidate.lua_quality["summary"].get("quality_gate_pass")
        return candidate.validation.ok and quality_gate is not False

    def generate(self, prompt: str, model: str | None = None, mode: str | None = None) -> GenerationResult:
        model_name = (model or self.settings.default_model).strip()
        self.client.ensure_model_allowed(model_name)

        request_mode_override = (
            mode if mode in {"direct_generation", "clarify_then_generate", "generate_then_repair"} else None
        )
        benchmark_mode = self.resolve_benchmark_mode(mode if mode and mode.upper().startswith("R") else None)
        include_rules, include_examples, allow_repair = self._mode_settings(benchmark_mode)

        request_mode = self.classify_request_mode(prompt, override=request_mode_override)
        plan = plan_task(prompt)
        if plan.needs_clarification and request_mode == "direct_generation":
            request_mode = "clarify_then_generate"
        output_contract = plan.output_contract
        context = self.retriever.retrieve_context(
            prompt,
            include_rules=include_rules,
            include_examples=include_examples,
            top_k=2,
        )

        LOGGER.info("generation_start model=%s request_mode=%s benchmark_mode=%s", model_name, request_mode, benchmark_mode)
        initial_candidates: list[CandidateAssessment] = []
        temperatures = [0.05, 0.15, 0.25]
        for index, strategy in enumerate(self._candidate_strategies()):
            generation_messages = build_generation_messages(
                prompt,
                context,
                plan,
                request_mode,
                output_contract,
                candidate_strategy=strategy,
            )
            response = self.client.chat(
                model_name,
                generation_messages,
                options=self._chat_options(
                    temperature=temperatures[min(index, len(temperatures) - 1)],
                    top_p=0.85 if index == 0 else 0.9,
                ),
            )
            initial_candidates.append(
                self._assess_candidate(
                    raw_output=response.content,
                    prompt=prompt,
                    output_contract=output_contract,
                    plan=plan,
                    strategy=strategy,
                )
            )

        best_initial = self._pick_best_candidate(initial_candidates)
        raw_output = best_initial.raw_output
        repaired_output: str | None = None
        final_candidate = best_initial
        used_repair = False

        if allow_repair and (not self._candidate_is_acceptable(best_initial)) and self.settings.repair_max_passes > 0:
            current = best_initial
            for _ in range(self.settings.repair_max_passes):
                validator_errors = self._candidate_issue_strings(current)
                if not validator_errors:
                    break

                repair_messages = build_repair_messages(
                    prompt,
                    current.code,
                    validator_errors,
                    context,
                    plan,
                    output_contract=output_contract,
                )
                repair_response = self.client.chat(
                    model_name,
                    repair_messages,
                    options=self._chat_options(temperature=0.05, top_p=0.9),
                )
                repaired_output = repair_response.content
                repaired_candidate = self._assess_candidate(
                    raw_output=repaired_output,
                    prompt=prompt,
                    output_contract=output_contract,
                    plan=plan,
                    strategy="targeted_repair",
                )
                best_after_repair = self._pick_best_candidate([current, repaired_candidate])
                if best_after_repair == current:
                    break
                current = best_after_repair
                used_repair = True
                if self._candidate_is_acceptable(current):
                    break
            final_candidate = current

        LOGGER.info(
            "generation_end model=%s ok=%s issues=%s used_repair=%s",
            model_name,
            final_candidate.validation.ok,
            len(final_candidate.validation.all_issues),
            used_repair,
        )

        return GenerationResult(
            code=final_candidate.code,
            model=model_name,
            request_mode=request_mode,
            benchmark_mode=benchmark_mode,
            raw_output=raw_output,
            repaired_output=repaired_output,
            validation=final_candidate.validation,
            used_repair=used_repair,
            plan=plan,
        )

    def generate_agent(
        self,
        prompt: str,
        model: str | None = None,
        mode: str | None = None,
        assumption: str | None = None,
    ) -> AgentIterationResult:
        plan = plan_task(prompt)
        request_mode = self.classify_request_mode(prompt, override=mode)

        if plan.needs_clarification and request_mode == "clarify_then_generate" and not assumption:
            model_name = model or self.settings.default_model
            self.client.ensure_model_allowed(model_name)
            return AgentIterationResult(
                status="clarification_required",
                code=None,
                model=model_name,
                request_mode=request_mode,
                benchmark_mode=self.resolve_benchmark_mode(None),
                used_repair=False,
                validation=None,
                question=self.clarification_question(plan),
                acceptable_assumptions=self.clarification_assumptions(plan),
                assumptions=plan.assumptions,
                output_contract=plan.output_contract,
            )

        prompt_for_generation = prompt
        if assumption in {"raw_lua", "json_with_lua_wrappers"}:
            if assumption == "raw_lua":
                prompt_for_generation = f"{prompt}\n\nAssumption: output must be raw Lua without JSON wrappers."
            else:
                prompt_for_generation = f"{prompt}\n\nAssumption: output must be JSON with lua{{...}}lua wrappers."

        generation_result = self.generate(prompt_for_generation, model=model, mode=mode)
        status = "repaired" if generation_result.used_repair else "generated"
        return AgentIterationResult(
            status=status,
            code=generation_result.code,
            model=generation_result.model,
            request_mode=generation_result.request_mode,
            benchmark_mode=generation_result.benchmark_mode,
            used_repair=generation_result.used_repair,
            validation=generation_result.validation,
            assumptions=generation_result.plan.assumptions,
            output_contract=generation_result.plan.output_contract,
        )

    def repair_with_feedback(
        self,
        prompt: str,
        previous_code: str,
        feedback: str,
        model: str | None = None,
        assumption: str | None = None,
    ) -> AgentIterationResult:
        model_name = model or self.settings.default_model
        model_name = model_name.strip()
        self.client.ensure_model_allowed(model_name)

        plan = plan_task(prompt)
        output_contract = assumption if assumption in {"raw_lua", "json_with_lua_wrappers"} else plan.output_contract
        context = self.retriever.retrieve_context(prompt, include_rules=True, include_examples=True, top_k=2)
        repair_messages = build_feedback_repair_messages(
            prompt=prompt,
            previous_code=previous_code,
            feedback=feedback,
            context=context,
            plan=plan,
            output_contract=output_contract,
        )
        response = self.client.chat(model_name, repair_messages)
        primary_candidate = self._assess_candidate(
            raw_output=previous_code,
            prompt=prompt,
            output_contract=output_contract,
            plan=plan,
            strategy="previous_code",
        )
        repaired_candidate = self._assess_candidate(
            raw_output=response.content,
            prompt=prompt,
            output_contract=output_contract,
            plan=plan,
            strategy="feedback_repair",
        )
        final_candidate = self._pick_best_candidate([primary_candidate, repaired_candidate])
        used_repair = final_candidate == repaired_candidate and final_candidate.code != primary_candidate.code
        return AgentIterationResult(
            status="repaired" if used_repair else "generated",
            code=final_candidate.code,
            model=model_name,
            request_mode="clarify_then_generate",
            benchmark_mode=self.resolve_benchmark_mode(None),
            used_repair=used_repair,
            validation=final_candidate.validation,
            assumptions=plan.assumptions,
            output_contract=output_contract,
        )
