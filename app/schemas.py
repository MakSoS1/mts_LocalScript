from enum import Enum

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Natural language task")
    model: str | None = Field(default=None, description="Optional model override")
    mode: str | None = Field(
        default=None,
        description="Pipeline mode override: R0/R1/R2/R3 or direct/clarify/repair",
    )


class GenerateResponse(BaseModel):
    code: str
    validation: ValidationReportFull | None = None
    quality_gate: QualityGateResult | None = None
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    latency_ms: float | None = None
    used_repair: bool | None = None
    request_mode: str | None = None
    task_type: str | None = None
    candidates_generated: int | None = None
    ir_used: bool | None = None


class AgentGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Natural language task")
    model: str | None = Field(default=None, description="Optional model override")
    mode: str | None = Field(
        default="clarify_then_generate",
        description="Agent mode override: direct_generation|clarify_then_generate|generate_then_repair",
    )
    assumption: str | None = Field(
        default=None,
        description="Optional accepted assumption: raw_lua|json_with_lua_wrappers",
    )
    feedback: str | None = Field(
        default=None,
        description="Optional follow-up instruction for minimal-delta repair.",
    )
    previous_code: str | None = Field(
        default=None,
        description="Previous code to repair when feedback is provided.",
    )


class ValidationDetail(BaseModel):
    ok: bool
    issues: list[dict] = Field(default_factory=list)


class ValidationReportFull(BaseModel):
    output: ValidationDetail = Field(default_factory=lambda: ValidationDetail(ok=True))
    contract: ValidationDetail = Field(default_factory=lambda: ValidationDetail(ok=True))
    domain: ValidationDetail = Field(default_factory=lambda: ValidationDetail(ok=True))
    syntax: ValidationDetail = Field(default_factory=lambda: ValidationDetail(ok=True))
    task: ValidationDetail | None = None


class PipelineStep(BaseModel):
    name: str
    status: str = "pending"
    duration_ms: float | None = None
    detail: str | None = None


class QualityGateResult(BaseModel):
    syntax_pass: bool | None = None
    lint_pass: bool | None = None
    format_pass: bool | None = None
    quality_gate_pass: bool | None = None


class AgentGenerateResponse(BaseModel):
    status: str
    code: str | None = None
    question: str | None = None
    acceptable_assumptions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    output_contract: str | None = None
    used_repair: bool = False
    request_mode: str | None = None
    benchmark_mode: str | None = None
    task_type: str | None = None
    confidence: float | None = None
    needs_clarification: bool | None = None
    plan: dict | None = None
    validation: ValidationReportFull | None = None
    quality_gate: QualityGateResult | None = None
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    latency_ms: float | None = None
    candidates_generated: int | None = None
    ir_used: bool | None = None
    kb_rules_used: bool | None = None
    kb_examples_used: bool | None = None
    kb_examples_count: int | None = None
    repair_iterations: int | None = None
    repair_issues: list[dict] | None = None


class VramInfo(BaseModel):
    model: str
    vram_used_mb: float | None = None
    vram_total_mb: float | None = None
    load_percent: float | None = None
    available: bool = True


class ResourceResponse(BaseModel):
    ollama_ok: bool
    running_models: list[str]
    vram: list[VramInfo] = Field(default_factory=list)
    cpu_percent: float | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None


class HealthResponse(BaseModel):
    status: str
    ollama_ok: bool
    active_models: list[str]
    default_model: str
    required_demo_model: str
    optional_benchmark_models: list[str]
    allowed_models: list[str]
    missing_required_models: list[str]
    missing_optional_models: list[str]


class BenchmarkMode(str, Enum):
    r0 = "R0"
    r1 = "R1"
    r2 = "R2"
    r3 = "R3"


class BenchmarkRequest(BaseModel):
    model: str
    dataset: str = Field(description="Path to JSONL dataset")
    mode: BenchmarkMode = BenchmarkMode.r3


class BenchmarkSummary(BaseModel):
    total_cases: int
    avg_total_score: float
    semantic_pass_rate: float
    domain_pass_rate: float
    syntax_pass_rate: float
    format_pass_rate: float
    avg_latency_ms: float


class BenchmarkResponse(BaseModel):
    run_id: str
    model: str
    mode: BenchmarkMode
    summary: BenchmarkSummary
    report_json: str
    report_markdown: str
