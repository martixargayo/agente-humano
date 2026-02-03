# backend/negotiation/response_validator.py
from __future__ import annotations

from typing import Tuple

from .elementos.render.validator_rules import evaluate_critical_violations
from .schemas import PolicyDecision, WorldState
from .validator import validate_and_repair as _validate_and_repair


def validate_response(
    text: str,
    constraints_struct: dict | None,
) -> list[str]:
    violations, _critical = evaluate_critical_violations(text)
    return [violation.get("code", "") for violation in violations if violation.get("code")]


def validate_and_repair(
    response_text: str,
    constraints_struct: dict | None,
    policy_decision: PolicyDecision,
    world_state: WorldState,
) -> Tuple[str, list[dict], dict]:
    return _validate_and_repair(
        response_text,
        constraints_struct,
        policy_decision,
        world_state,
    )
