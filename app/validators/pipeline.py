from app.validators.contract_validator import validate_contract
from app.validators.domain_validator import validate_domain
from app.validators.output_validator import validate_output
from app.validators.syntax_validator import validate_syntax
from app.validators.task_validator import validate_task_specific
from app.validators.types import ValidationBundle


def run_all_validators(
    code: str,
    prompt: str,
    luac_binary: str = "luac5.4",
    expected_contract: str | None = None,
    syntax_require_luac: bool = False,
    task_type: str | None = None,
) -> ValidationBundle:
    output = validate_output(code)
    contract = validate_contract(code, expected_contract=expected_contract)
    domain = validate_domain(code, prompt)
    syntax = validate_syntax(code, luac_binary, require_luac=syntax_require_luac)
    task = validate_task_specific(code, task_type)
    return ValidationBundle(output=output, contract=contract, domain=domain, syntax=syntax, task=task)
