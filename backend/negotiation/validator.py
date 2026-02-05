from __future__ import annotations

from typing import Tuple

from .elementos.render.validator_rules import evaluate_critical_violations
from .schemas import PersonaProfile, PolicyDecision, SceneProfile, StyleContract, WorldState


def safe_neutral_fallback(
    persona: PersonaProfile | None = None,
    scene: SceneProfile | None = None,
    style: StyleContract | None = None,
) -> str:
    max_questions = 1
    if style:
        try:
            max_questions = int(style.get("max_questions", max_questions))
        except (TypeError, ValueError):
            max_questions = 1
    if max_questions <= 0:
        return "Puedo ayudarte, pero necesito más contexto para responder con precisión."
    return "Puedo ayudarte, pero necesito que me confirmes qué necesitas exactamente y con qué contexto."


def validate_and_repair(
    response_text: str,
    constraints_struct: dict | None,
    policy_decision: PolicyDecision,
    world_state: WorldState,
    *,
    persona_profile: PersonaProfile | None = None,
    scene_profile: SceneProfile | None = None,
    style_contract: StyleContract | None = None,
) -> Tuple[str, list[dict], dict]:
    violations, critical = evaluate_critical_violations(response_text)
    meta = {
        "violations": violations,
        "critical": critical,
        "fallback_applied": False,
    }
    if not critical:
        return response_text, violations, meta

    fallback = safe_neutral_fallback(persona_profile, scene_profile, style_contract)
    meta["fallback_applied"] = True
    meta["override_reason"] = "validator_critical_fallback"
    return fallback, violations, meta
