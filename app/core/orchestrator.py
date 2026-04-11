from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.core.model_client import OllamaClient
from app.core.planner import TaskPlan, plan_task
from app.core.prompts import (
    build_generation_messages,
    build_repair_messages,
)
from app.core.repair import select_best_candidate
from app.core.retrieval import LocalRetriever
from app.utils.extract_code import normalize_output_contract
from app.utils.logging import get_logger
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

    def generate(self, prompt: str, model: str | None = None, mode: str | None = None) -> GenerationResult:
        model_name = model or self.settings.default_model
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
        generation_messages = build_generation_messages(
            prompt,
            context,
            plan,
            request_mode,
            output_contract,
        )
        first_response = self.client.chat(model_name, generation_messages)
        raw_output = first_response.content
        first_code = normalize_output_contract(
            raw_output,
            output_contract,
            preferred_keys=plan.output_keys,
            force_json_wrap=plan.confidence >= 0.85,
        )
        first_validation = run_all_validators(
            first_code,
            prompt,
            self.settings.luac_binary,
            expected_contract=output_contract,
            syntax_require_luac=self.settings.syntax_require_luac,
            task_type=plan.task_type,
        )

        repaired_output: str | None = None
        final_code = first_code
        final_validation = first_validation
        used_repair = False

        if allow_repair and (not first_validation.ok) and self.settings.repair_max_passes > 0:
            validator_errors = [f"{issue.validator}:{issue.code}:{issue.hint}" for issue in first_validation.all_issues]
            repair_messages = build_repair_messages(
                prompt,
                first_code,
                validator_errors,
                context,
                plan,
                output_contract=output_contract,
            )
            repair_response = self.client.chat(model_name, repair_messages)
            repaired_output = repair_response.content
            repaired_code = normalize_output_contract(
                repaired_output,
                output_contract,
                preferred_keys=plan.output_keys,
                force_json_wrap=plan.confidence >= 0.85,
            )
            repaired_validation = run_all_validators(
                repaired_code,
                prompt,
                self.settings.luac_binary,
                expected_contract=output_contract,
                syntax_require_luac=self.settings.syntax_require_luac,
                task_type=plan.task_type,
            )
            final_code, final_validation, used_repair = select_best_candidate(
                first_code,
                first_validation,
                repaired_code,
                repaired_validation,
            )

        LOGGER.info(
            "generation_end model=%s ok=%s issues=%s used_repair=%s",
            model_name,
            final_validation.ok,
            len(final_validation.all_issues),
            used_repair,
        )

        return GenerationResult(
            code=final_code,
            model=model_name,
            request_mode=request_mode,
            benchmark_mode=benchmark_mode,
            raw_output=raw_output,
            repaired_output=repaired_output,
            validation=final_validation,
            used_repair=used_repair,
            plan=plan,
        )
