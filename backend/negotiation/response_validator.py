# backend/negotiation/response_validator.py
from __future__ import annotations

import logging
import os
from typing import Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .elementos.execution_definitions import (
    NUMBER_PATTERN,
    OWN_NUMBER_CONTEXT,
    PRICE_CONTEXT,
)
from .policies import safe_neutral_policy_id
from .schemas import PolicyDecision, WorldState


logger = logging.getLogger(__name__)


def _parse_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_PATTERN.findall(text):
        cleaned = match.replace(".", "").replace(",", ".")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def _extract_price_like_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_PATTERN.finditer(text):
        span = match.span()
        window = text[max(0, span[0] - 25) : min(len(text), span[1] + 25)]
        if PRICE_CONTEXT.search(window):
            cleaned = match.group(0).replace(".", "").replace(",", ".")
            try:
                values.append(float(cleaned))
            except ValueError:
                continue
    return values


def _violates_own_number_rule(text: str) -> bool:
    if not OWN_NUMBER_CONTEXT.search(text):
        return False
    return bool(_parse_numbers(text))


def _violates_max_total_cost(text: str, max_total_cost: float) -> bool:
    if max_total_cost <= 0:
        return False
    values = _extract_price_like_numbers(text)
    if not values:
        return False
    return any(value > max_total_cost for value in values)


def validate_response(
    text: str,
    constraints_struct: dict | None,
) -> list[str]:
    constraints = constraints_struct or {}
    max_total_cost = float(constraints.get("max_total_cost", 0.0) or 0.0)
    violations: list[str] = []
    if constraints.get("avoid_reveal_own_numbers") and _violates_own_number_rule(text):
        violations.append("reveal_own_numbers")
    if constraints.get("respect_batna") and _violates_max_total_cost(text, max_total_cost):
        violations.append("exceed_max_total_cost")
    return violations


def validate_and_repair(
    response_text: str,
    constraints_struct: dict | None,
    policy_decision: PolicyDecision,
    world_state: WorldState,
) -> Tuple[str, list[str], dict]:
    violations = validate_response(response_text, constraints_struct)
    meta = {
        "violations": violations,
        "repaired_used": False,
        "model": "",
    }
    if not violations:
        return response_text, [], meta

    model = os.getenv("RESPONSE_VALIDATOR_MODEL", os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"))
    llm = ChatOpenAI(model=model, temperature=0.0)
    meta["model"] = model
    constraints = constraints_struct or {}
    max_total_cost = float(constraints.get("max_total_cost", 0.0) or 0.0)
    policy_id = policy_decision.get("policy_id", "")
    prompt = (
        "Reescribe la respuesta del comprador eliminando violaciones de guardrails.\n"
        "- No reveles números propios (presupuesto/oferta propia).\n"
        f"- No aceptes por encima de {max_total_cost:.0f}€ si aplica.\n"
        "- Mantén el tono y la intención de la policy.\n"
        "- Máximo 2 frases, una pregunta al final.\n"
    )
    user = (
        f"[Policy]: {policy_id}\n"
        f"[WorldState]: {world_state}\n"
        f"[Violations]: {violations}\n"
        f"[Original]: {response_text}\n"
    )
    messages = [SystemMessage(content=prompt), HumanMessage(content=user)]
    repaired = llm.invoke(messages)
    meta["repaired_used"] = True
    new_text = getattr(repaired, "content", str(repaired)).strip()
    remaining = validate_response(new_text, constraints_struct)
    if remaining:
        logger.warning("response_validator_repair_failed=%s", remaining)
        safe = (
            "Prefiero no comprometer cifras ahora; antes quiero confirmar un par de detalles. "
            "¿Qué incluye exactamente el precio y qué papeles tienes a mano?"
        )
        meta["override_policy_id"] = safe_neutral_policy_id()
        meta["override_reason"] = "validator_fallback_safe_text"
        return safe, remaining, meta
    return new_text, violations, meta
