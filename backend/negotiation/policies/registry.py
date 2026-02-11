# backend/negotiation/policies.py
from __future__ import annotations

from typing import List

from ..elementos.strategy_definitions import POLICIES, Policy


def list_policy_ids() -> List[str]:
    return [policy.policy_id for policy in POLICIES]


def safe_neutral_policy_id() -> str:
    ids = list_policy_ids()
    if "safe_neutral" in ids:
        return "safe_neutral"
    if "rapport_build" in ids:
        return "rapport_build"
    return ids[0] if ids else "safe_neutral"


def policy_catalog_text() -> str:
    lines = []
    for policy in POLICIES:
        phase_hints = ",".join(policy.phase_hints)
        lines.append(
            f"- {policy.policy_id}: {policy.description} | Cuándo: {policy.primary_when} | "
            f"Fases: {phase_hints} | Required: {policy.required_inputs} | "
            f"Target slots: {policy.target_slots} | Expected: {policy.expected_effects} | "
            f"Failure: {policy.failure_modes}"
        )
    return "\n".join(lines)


def policy_catalog_with_phases_text() -> str:
    lines = []
    for policy in POLICIES:
        phases = ", ".join(policy.phase_hints)
        required = policy.required_inputs or []
        lines.append(
            f"- {policy.policy_id}: {policy.description} | Phases: {phases} | "
            f"Required inputs: {required}"
        )
    return "\n".join(lines)


def policy_phase_catalog() -> dict[str, list[str]]:
    return {policy.policy_id: list(policy.phase_hints) for policy in POLICIES}


def get_policy(policy_id: str) -> Policy | None:
    for policy in POLICIES:
        if policy.policy_id == policy_id:
            return policy
    return None
