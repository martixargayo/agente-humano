from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from langchain_core.prompts import ChatPromptTemplate

from prompts import PHASE_POLICY_SYSTEM_PROMPT, PHASE_POLICY_USER_PROMPT
from .config import get_negotiation_model_config
from .elementos.strategy_definitions import PhasePolicyDecisionModel, REASON_PREFIXES
from .llm_clients import get_planner_llm
from .policies import safe_neutral_policy_id
from .schemas import BeliefState, PolicyDecision, ProgressState, WorldState, default_policy_decision
from .validation import normalize_policy_decision
from .telemetry.llm_usage import extract_llm_usage

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
    return normalized[:6]


def _compact_world_summary(world_state: WorldState) -> dict:
    buckets = (world_state or {}).get("world_buckets", {}) if isinstance(world_state, dict) else {}
    return {
        "offers": list((buckets.get("offers") or []))[:2],
        "constraints": list((buckets.get("constraints") or []))[:2],
        "interests": list((buckets.get("interests") or []))[:2],
        "requests": list((buckets.get("requests") or []))[:2],
    }


def _compact_belief_summary(belief_state: BeliefState) -> dict:
    planner = (belief_state or {}).get("planner_signals", {}) if isinstance(belief_state, dict) else {}
    buckets = (belief_state or {}).get("belief_buckets", {}) if isinstance(belief_state, dict) else {}
    return {
        "planner_signals": planner,
        "hypotheses": list((buckets.get("hypotheses") or []))[:3],
        "risk_flags": list((buckets.get("risk_flags") or []))[:3],
    }


def _fallback_policy(allowed_ids: list[str]) -> PolicyDecision:
    fallback_id = safe_neutral_policy_id()
    if fallback_id not in allowed_ids and allowed_ids:
        fallback_id = allowed_ids[0]
    out = default_policy_decision()
    out["policy_id"] = fallback_id
    out["reason"] = "Fallback seguro por error de planner."
    out["micro_goal"] = "Mantener conversación abierta con una pregunta breve."
    out["risk_posture"] = "low"
    return out


def _fallback_plan(allowed_ids: list[str]) -> dict:
    policy_id = safe_neutral_policy_id() if safe_neutral_policy_id() in allowed_ids else (allowed_ids[0] if allowed_ids else "safe_neutral")
    return {
        "plan_id": "plan_fallback",
        "current_step_idx": 0,
        "context_digest": "Mantener claridad y pedir señal verificable.",
        "steps": [
            {
                "step_idx": 0,
                "micro_goal": "Validar propuesta actual",
                "what_to_do": f"Aplicar {policy_id} y pedir una aclaración concreta.",
                "ask": ["¿Qué dato verificable podemos cerrar ahora?"],
                "success_criteria": ["nueva_informacion_verificable"],
                "replan_triggers": ["ambiguedad_persistente"],
                "safe_mode": "normal",
            },
            {
                "step_idx": 1,
                "micro_goal": "Consolidar siguiente acción",
                "what_to_do": "Resumir acuerdo parcial y proponer siguiente paso.",
                "ask": ["¿Te parece bien este siguiente paso?"],
                "success_criteria": ["confirmacion_de_paso"],
                "replan_triggers": ["contradiccion"],
                "safe_mode": "normal",
            },
        ],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": ["escalar_tension"], "stop_conditions": ["amenaza"]},
    }


def _to_active_plan(payload_plan: dict, turn_count: int) -> dict:
    steps_out = []
    for idx, step in enumerate(list(payload_plan.get("steps") or [])[:5]):
        if not isinstance(step, dict):
            continue
        step_idx = int(step.get("step_idx", idx) or idx)
        steps_out.append(
            {
                "step_idx": max(0, step_idx),
                "micro_goal": str(step.get("goal", ""))[:160],
                "what_to_do": str(step.get("instruction", ""))[:260],
                "ask": [],
                "success_criteria": [str(x)[:80] for x in list(step.get("success_criteria") or [])[:3]],
                "replan_triggers": ["ambiguedad_persistente", "escalada"],
                "safe_mode": "normal",
            }
        )
    if len(steps_out) < 2:
        return _fallback_plan([safe_neutral_policy_id()])
    cur = int(payload_plan.get("current_step_idx", 0) or 0)
    cur = max(0, min(cur, len(steps_out) - 1))
    plan_id = str(payload_plan.get("plan_id", "") or f"plan_t{turn_count}")[:40]
    return {
        "phase_assessment": {},
        "schema_version": "v1",
        "plan_id": plan_id,
        "created_turn": turn_count,
        "updated_turn": turn_count,
        "horizon_turns": len(steps_out),
        "current_step_idx": cur,
        "global_goal": str(payload_plan.get("context_digest", ""))[:180],
        "steps": steps_out,
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": ["escalar_tension"], "stop_conditions": ["amenaza"]},
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
    advisor_recs: dict | None = None,
) -> tuple[dict, PolicyDecision, dict]:
    del world_diff, policy_plan_summary, constraints_struct
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
        "active_plan": None,
        "planner_input_prompt_rendered": "",
        "planner_input_payload_raw": None,
        "planner_output_text_rendered": "",
        "planner_output_payload_raw": None,
    }

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    try:
        messages = _planner_prompt.format_messages(
            objective=objective,
            constraints=constraints,
            recent_context=recent_context,
            phase_state=json.dumps(progress_state.get("phase_state", {}), ensure_ascii=False),
            active_plan=json.dumps(progress_state.get("active_plan", {}) or {}, ensure_ascii=False),
            policy_state=json.dumps(policy_state or {}, ensure_ascii=False),
            allowed_policy_ids=json.dumps(allowed_policy_ids, ensure_ascii=False),
            world_summary=json.dumps(_compact_world_summary(world_state), ensure_ascii=False),
            belief_summary=json.dumps(_compact_belief_summary(belief_state), ensure_ascii=False),
            advisor_recs=json.dumps(advisor_recs or {}, ensure_ascii=False),
        )
        structured = get_planner_llm().with_structured_output(PhasePolicyDecisionModel)
        meta["planner_input_payload_raw"] = [
            {"role": getattr(msg, "type", "user"), "content": str(getattr(msg, "content", ""))}
            for msg in messages
        ]
        meta["planner_input_prompt_rendered"] = "\n\n".join(
            f"[{item['role']}]\n{item['content']}" for item in meta["planner_input_payload_raw"]
        )

        result = structured.invoke(messages)
        ended_wall = datetime.now(timezone.utc).isoformat()
        usage = extract_llm_usage(result)
        meta["planner_llm_called"] = True
        payload = result.model_dump()
        meta["planner_output_payload_raw"] = payload
        meta["planner_output_text_rendered"] = json.dumps(payload, ensure_ascii=False)
        phase_candidate = {
            "phase": payload.get("phase", "climate"),
            "confidence": float(payload.get("confidence", 0.6) or 0.6),
            "recovery_mode": bool(payload.get("recovery_mode", False)),
            "reasons": _normalize_reasons(payload.get("reasons", [])),
            "signals": [],
            "alternatives": [],
        }
        policy_decision = {
            "policy_id": str(payload.get("policy_id", "")),
            "reason": str(payload.get("reason", "")),
            "micro_goal": str(payload.get("micro_goal", "")),
            "risk_posture": payload.get("risk_posture", "low"),
            "why_short": str(payload.get("why_short", "")),
            "inputs_used": [],
        }
        normalized, issues = normalize_policy_decision(policy_decision, allowed_policy_ids)
        if issues:
            meta["policy_normalization_changed"] = True
            meta["issues"].extend(issues)
        if normalized.get("policy_id") not in allowed_policy_ids and allowed_policy_ids:
            normalized["policy_id"] = allowed_policy_ids[0]
            meta["policy_normalization_changed"] = True
        payload_plan = payload.get("active_plan") if isinstance(payload.get("active_plan"), dict) else {}
        meta["active_plan"] = _to_active_plan(payload_plan, int(progress_state.get("last_progress_update_turn", 0) or 0) + 1)
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_start_ts"] = started_wall
        meta["planner_end_ts"] = ended_wall
        meta["planner_model"] = usage.get("model")
        meta["planner_tokens_in"] = usage.get("tokens_in")
        meta["planner_tokens_out"] = usage.get("tokens_out")
        meta["planner_queue_ms"] = usage.get("queue_ms")
        meta["planner_ttfb_ms"] = usage.get("ttfb_ms")
        return phase_candidate, normalized, meta
    except Exception as exc:
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["planner_llm_called"] = True
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_start_ts"] = started_wall
        meta["planner_end_ts"] = ended_wall
        meta["planner_failed"] = True
        meta["planner_fallback_used"] = True
        meta["planner_error"] = str(exc)
        meta["planner_error_stage"] = "prompt_format" if isinstance(exc, (KeyError, ValueError)) else "llm_invoke"
        meta["issues"].append("planner_exception")
        meta["active_plan"] = _fallback_plan(allowed_policy_ids)
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
