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


class AgentGenerateResponse(BaseModel):
    status: str
    code: str | None = None
    question: str | None = None
    acceptable_assumptions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    output_contract: str | None = None
    used_repair: bool = False


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
