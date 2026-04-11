from __future__ import annotations

from app.validators.types import ValidationBundle


def select_best_candidate(
    primary_code: str,
    primary_validation: ValidationBundle,
    repaired_code: str,
    repaired_validation: ValidationBundle,
) -> tuple[str, ValidationBundle, bool]:
    if repaired_validation.ok and not primary_validation.ok:
        return repaired_code, repaired_validation, True
    if repaired_validation.ok and primary_validation.ok:
        return primary_code, primary_validation, False
    if len(repaired_validation.all_issues) < len(primary_validation.all_issues):
        return repaired_code, repaired_validation, True
    return primary_code, primary_validation, False
