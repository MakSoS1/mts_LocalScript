from dataclasses import dataclass, field


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    hint: str
    validator: str


@dataclass(slots=True)
class ValidationReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass(slots=True)
class ValidationBundle:
    output: ValidationReport
    contract: ValidationReport
    domain: ValidationReport
    syntax: ValidationReport
    task: ValidationReport | None = None

    @property
    def ok(self) -> bool:
        return self.output.ok and self.contract.ok and self.domain.ok and self.syntax.ok

    @property
    def all_issues(self) -> list[ValidationIssue]:
        task_issues = [] if self.task is None else self.task.issues
        return [
            *self.output.issues,
            *self.contract.issues,
            *self.domain.issues,
            *self.syntax.issues,
            *task_issues,
        ]
