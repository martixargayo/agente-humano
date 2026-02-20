from __future__ import annotations

import json
import logging
import time

from langchain_core.prompts import ChatPromptTemplate
from prompts import PHASE_POLICY_SYSTEM_PROMPT, PHASE_POLICY_USER_PROMPT
from .config import get_negotiation_model_config
from .llm_clients import get_planner_llm
from .elementos.strategy_definitions import PhasePolicyDecisionModel, REASON_PREFIXES
from .policies import get_policy, policy_catalog_text, policy_catalog_with_phases_text, safe_neutral_policy_id
from .schemas import (
    BeliefState,
    NegotiationPhase,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_policy_decision,
)
from .validation import normalize_policy_decision
from env_compat import getenv_float_preferred, getenv_preferred

logger = logging.getLogger(__name__)


NEGOTIATION_CONFIG = get_negotiation_model_config()
PLANNER_MODEL = NEGOTIATION_CONFIG.planner.model
PLANNER_TEMPERATURE = NEGOTIATION_CONFIG.planner.temperature


_planner_prompt = ChatPromptTemplate.from_messages(
    [("system", PHASE_POLICY_SYSTEM_PROMPT), ("user", PHASE_POLICY_USER_PROMPT)]
)


def _normalize_reasons(reasons: list[str]) -> list[str]:
    normalized: list[str] = []
    for reason in reasons or []:
        raw = str(reason).strip()
        if not raw:
            continue
        if ":" in raw:
            prefix, rest = raw.split(":", 1)
            if prefix in REASON_PREFIXES and rest.strip():
                normalized.append(f"{prefix}:{rest.strip()}"[:64])
                continue
        key = raw.replace(" ", "_")[:48] or "unspecified"
        normalized.append(f"history:{key}"[:64])
    return normalized[:8]


def _normalize_signals(signals: list[dict]) -> list[dict]:
    out: list[dict] = []
    for signal in signals or []:
        if not isinstance(signal, dict):
            continue
        source = str(signal.get("source", "")).strip()
        if source not in REASON_PREFIXES:
            continue
        key = str(signal.get("key", "")).strip()[:48]
        value = str(signal.get("value", "")).strip()[:120]
        if not key or not value:
            continue
        out.append({"source": source, "key": key, "value": value})
        if len(out) >= 8:
            break
    return out


def _fallback_policy(allowed_ids: list[str]) -> PolicyDecision:
    fallback_id = safe_neutral_policy_id()
    if fallback_id not in allowed_ids and allowed_ids:
        fallback_id = allowed_ids[0]
    return {
        "policy_id": fallback_id,
        "reason": "Fallback seguro por error de planner.",
        "micro_goal": "Mantener conversación abierta con una pregunta breve.",
        "risk_posture": "low",
    }


def _policy_plan_summary(progress_state: ProgressState) -> dict:
    policy_state = progress_state.get("policy_state", {}) if isinstance(progress_state, dict) else {}
    policy_id = policy_state.get("policy_id", "")
    if not policy_id:
        return {}
    policy = get_policy(policy_id)
    plan = policy.plan if policy else None
    if not plan:
        return {"policy_id": policy_id, "steps": []}
    steps = []
    for idx, step in enumerate(plan.steps):
        steps.append(
            {
                "idx": idx,
                "kind": step.kind,
                "target_slot": step.target_slot,
                "micro_goal": step.micro_goal[:80],
            }
        )
    return {"policy_id": policy_id, "steps": steps}




def _belief_cues_governed(belief_state: BeliefState) -> dict:
    if not isinstance(belief_state, dict):
        return {
            "behavior_guidance": {},
            "interaction_health": "stable",
            "risk_flags": [],
            "strategy_notes": [],
        }
    planner = belief_state.get("planner_signals", {}) if isinstance(belief_state.get("planner_signals"), dict) else {}
    buckets = belief_state.get("belief_buckets", {}) if isinstance(belief_state.get("belief_buckets"), dict) else {}
    risk_flags = buckets.get("risk_flags", []) if isinstance(buckets.get("risk_flags"), list) else []
    strategy_notes = buckets.get("strategy_notes", []) if isinstance(buckets.get("strategy_notes"), list) else []
    return {
        "behavior_guidance": {},
        "interaction_health": planner.get("interaction_health", "stable"),
        "risk_flags": risk_flags[:3],
        "strategy_notes": strategy_notes[:3],
    }
def plan_phase_policy(
    world_state: WorldState,
    world_diff: dict,
    belief_state: BeliefState,
    progress_state: ProgressState,
    policy_state: dict | None,
    policy_plan_summary: dict | None,
    objective: str,
    constraints: str,
    constraints_struct: dict | None = None,
    recent_context: str = "",
    allowed_policy_ids: list[str] | None = None,
) -> tuple[dict, PolicyDecision, dict]:
    allowed_policy_ids = list(allowed_policy_ids or [])
    if not allowed_policy_ids:
        allowed_policy_ids = [safe_neutral_policy_id()]

    meta = {
        "planner_llm_called": False,
        "planner_latency_ms": 0,
        "planner_failed": False,
        "planner_error": "",
        "planner_error_stage": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "issues": [],
        "allowed_policy_ids": allowed_policy_ids,
    }

    started = time.perf_counter()
    try:
        messages = _planner_prompt.format_messages(
            world_state=json.dumps(world_state, ensure_ascii=False),
            world_diff=json.dumps(world_diff or {}, ensure_ascii=False),
            belief_state=json.dumps(belief_state, ensure_ascii=False),
            belief_cues=json.dumps(_belief_cues_governed(belief_state), ensure_ascii=False),
            policy_state=json.dumps(policy_state or {}, ensure_ascii=False),
            policy_plan_summary=json.dumps(
                policy_plan_summary or _policy_plan_summary(progress_state), ensure_ascii=False
            ),
            phase_state=json.dumps(progress_state.get("phase_state", {}), ensure_ascii=False),
            allowed_policy_ids=json.dumps(allowed_policy_ids, ensure_ascii=False),
            policy_catalog=policy_catalog_text(),
            policy_catalog_with_phases=policy_catalog_with_phases_text(),
            objective=objective,
            constraints=constraints,
            recent_context=recent_context,
        )
        structured = get_planner_llm().with_structured_output(PhasePolicyDecisionModel)

        result = structured.invoke(messages)
        meta["planner_llm_called"] = True
        payload = result.model_dump()
        phase_candidate = {
            "phase": payload.get("phase", "climate"),
            "confidence": float(payload.get("confidence", 0.6) or 0.6),
            "recovery_mode": bool(payload.get("recovery_mode", False)),
            "reasons": _normalize_reasons(payload.get("reasons", [])),
            "signals": _normalize_signals(payload.get("signals", [])),
            "alternatives": payload.get("alternatives", []),
        }
        policy_decision = {
            "policy_id": str(payload.get("policy_id", "")),
            "reason": str(payload.get("reason", "")),
            "micro_goal": str(payload.get("micro_goal", "")),
            "risk_posture": payload.get("risk_posture", "low"),
            "why_short": str(payload.get("why_short", "")),
            "inputs_used": payload.get("inputs_used", []),
        }
        normalized, issues = normalize_policy_decision(policy_decision, allowed_policy_ids)
        if issues:
            meta["policy_normalization_changed"] = True
            meta["issues"].extend(issues)
        if normalized.get("policy_id") not in allowed_policy_ids and allowed_policy_ids:
            normalized["policy_id"] = allowed_policy_ids[0]
            meta["policy_normalization_changed"] = True
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        return phase_candidate, normalized, meta
    except Exception as exc:
        meta["planner_llm_called"] = True
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_failed"] = True
        meta["planner_fallback_used"] = True
        meta["planner_error"] = str(exc)
        meta["planner_error_stage"] = "prompt_format" if isinstance(exc, (KeyError, ValueError)) else "llm_invoke"
        meta["issues"].append("planner_exception")
        logger.warning("phase_policy_planner_error stage=%s detail=%s", meta["planner_error_stage"], exc)
        return (
            {
                "phase": "climate",
                "confidence": 0.0,
                "recovery_mode": False,
                "reasons": [],
                "signals": [],
                "alternatives": [],
            },
            _fallback_policy(allowed_policy_ids),
            meta,
        )
