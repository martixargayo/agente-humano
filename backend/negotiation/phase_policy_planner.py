from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from prompts import (
    PLANNER_V2_SYSTEM_PROMPT,
    PLANNER_V2_USER_PROMPT,
)
from .config import get_negotiation_model_config
from .elementos.strategy_definitions import PlannerV2DecisionModel
from .llm_planning_context import (
    PHASE_DEFINITIONS_ES,
    POLICY_CATALOG_ES,
    build_belief_digest,
    build_full_roleplay_profiles,
    build_objective_summary,
    build_planner_context_block_full,
    build_world_digest,
)
from .llm_clients import get_planner_llm
from .policies import safe_neutral_policy_id
from .schemas import BeliefState, PolicyDecision, ProgressState, WorldState, default_policy_decision
from .validation import normalize_policy_decision
from .telemetry.llm_usage import extract_llm_usage

logger = logging.getLogger(__name__)

NEGOTIATION_CONFIG = get_negotiation_model_config()
PLANNER_MODEL = NEGOTIATION_CONFIG.planner.model
PLANNER_TEMPERATURE = NEGOTIATION_CONFIG.planner.temperature

_planner_v2_prompt = ChatPromptTemplate.from_messages(
    [("system", PLANNER_V2_SYSTEM_PROMPT), ("user", PLANNER_V2_USER_PROMPT)]
)

PLANNER_POLICY_CATALOG_MAX_CHARS = 8500
PLANNER_POLICY_SUBSET_MAX_ITEMS = 8


def _compact_policy_catalog_for_prompt(catalog_subset: dict[str, dict], *, max_chars: int = PLANNER_POLICY_CATALOG_MAX_CHARS) -> str:
    full = json.dumps(catalog_subset if isinstance(catalog_subset, dict) else {}, ensure_ascii=False)
    if len(full) <= max_chars:
        return full

    compact: dict[str, dict] = {}
    for policy_id, item in (catalog_subset or {}).items():
        if not isinstance(item, dict):
            continue
        compact[str(policy_id)] = {
            "goal": str(item.get("goal", ""))[:180],
            "when_to_use": str(item.get("when_to_use", ""))[:200],
            "how_to_execute": [str(x)[:100] for x in list(item.get("how_to_execute", []) or [])[:2]],
            "avoid": [str(x)[:80] for x in list(item.get("avoid", []) or [])[:2]],
        }
    compact_text = json.dumps(compact, ensure_ascii=False)
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[:max_chars]


def _build_policy_catalog_subset(
    *,
    allowed_policy_ids: list[str],
    planner_request: str,
    policy_state: dict | None,
    advisor_recs: dict | None,
    judge_result: dict | None,
) -> tuple[dict[str, dict], list[str]]:
    allowed = [str(x) for x in (allowed_policy_ids or []) if str(x).strip()]
    catalog = POLICY_CATALOG_ES if isinstance(POLICY_CATALOG_ES, dict) else {}

    def _push(items: list[str], out: list[str]) -> None:
        for item in items:
            pid = str(item or "").strip()
            if not pid or pid in out:
                continue
            if pid in allowed and pid in catalog:
                out.append(pid)

    ranked: list[str] = []
    active_policy_id = str((policy_state or {}).get("policy_id", "") or "").strip()
    req = str(planner_request or "").strip()

    continue_mode = req == "continue_policy" and bool(active_policy_id)
    if continue_mode:
        _push([active_policy_id], ranked)
    else:
        advisor_text = json.dumps(advisor_recs or {}, ensure_ascii=False).lower()
        judge_missing = [str(x).lower() for x in list((judge_result or {}).get("missing_signals", []) or [])]

        if "proceso" in advisor_text or "decisión" in advisor_text:
            _push(["set_process_rules"], ranked)
        if "reset" in advisor_text:
            _push(["meta_negotiation_reset"], ranked)
        if "structured" in advisor_text or "choice" in advisor_text:
            _push(["repair_loop_structured_choice"], ranked)
        if any(key in advisor_text for key in ["clarificar", "detalle", "credibilidad", "sí/no", "si/no"]):
            _push(["clarify_missing_info"], ranked)

        if any(sig in {"precio", "condiciones", "documentacion", "mecanica"} for sig in judge_missing):
            _push(["clarify_missing_info", "repair_loop_structured_choice"], ranked)

    if "safe_neutral" in allowed and "safe_neutral" in catalog:
        _push(["safe_neutral"], ranked)

    if not continue_mode:
        _push(allowed, ranked)

    ranked = ranked[:PLANNER_POLICY_SUBSET_MAX_ITEMS]
    subset = {pid: catalog[pid] for pid in ranked if pid in catalog}
    if not subset:
        fallback_ids = [pid for pid in allowed if pid in catalog][:1]
        subset = {pid: catalog[pid] for pid in fallback_ids}
        ranked = fallback_ids
    return subset, ranked


def _is_length_parse_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "length limit was reached" in text
        or "could not parse response content" in text
        or "finish_reason='length'" in text
    )


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
                "intent_id": "clarify_current_state",
                "micro_goal": "Clarificar estado actual con información verificable",
                "what_to_do": f"Aplicar {policy_id} y pedir una aclaración concreta.",
                "ask": ["¿Qué dato verificable podemos cerrar ahora?"],
                "success_criteria": ["confirmar_intencion_con_info_nueva"],
                "replan_triggers": ["ambiguedad_persistente"],
                "safe_mode": "normal",
            },
            {
                "step_idx": 1,
                "intent_id": "confirm_next_step",
                "micro_goal": "Consolidar siguiente acción acordada",
                "what_to_do": "Resumir acuerdo parcial y proponer siguiente paso.",
                "ask": ["¿Te parece bien este siguiente paso?"],
                "success_criteria": ["acuerdo_sobre_siguiente_paso"],
                "replan_triggers": ["contradiccion"],
                "safe_mode": "normal",
            },
        ],
        "required_intents": ["clarify_current_state", "confirm_next_step"],
        "covered_intents": ["clarify_current_state", "confirm_next_step"],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": ["escalar_tension"], "stop_conditions": ["amenaza"]},
    }




def _normalize_intent_id(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    out = []
    prev_us = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
            prev_us = True
    norm = "".join(out).strip("_")[:64]
    return norm


def _to_active_plan(payload_plan: dict, turn_count: int) -> dict:
    steps_out = []
    covered_intents: list[str] = []
    for idx, step in enumerate(list(payload_plan.get("steps") or [])[:5]):
        if not isinstance(step, dict):
            continue
        step_idx = int(step.get("step_idx", idx) or idx)
        intent_id = _normalize_intent_id(step.get("intent_id"))
        success_criteria = [str(x)[:80] for x in list(step.get("success_criteria") or [])[:3]]
        if not success_criteria:
            success_criteria = ["intent_alineado_con_info_nueva"]
        steps_out.append(
            {
                "step_idx": max(0, step_idx),
                "intent_id": intent_id,
                "micro_goal": str(step.get("goal", ""))[:160],
                "what_to_do": str(step.get("instruction", ""))[:260],
                "ask": [],
                "success_criteria": success_criteria,
                "replan_triggers": ["ambiguedad_persistente", "escalada"],
                "safe_mode": "normal",
            }
        )
        if intent_id:
            covered_intents.append(intent_id)
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
        "required_intents": [str(x)[:64] for x in list(payload_plan.get("required_intents") or [])[:8]],
        "covered_intents": covered_intents[:8],
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
    judge_result: dict | None = None,
    memory_short: str = "",
    memory_long: str = "",
    pivot_required: bool = False,
) -> tuple[dict, PolicyDecision, dict]:
    del policy_plan_summary, constraints_struct, recent_context
    world_diff = world_diff if isinstance(world_diff, dict) else {}
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
        "policy_subset_ids": [],
        "policy_subset_chars": 0,
        "policy_subset_size": 0,
    }

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    try:
        full_profiles_block = build_planner_context_block_full(progress_state)
        persona_profile, scene_profile, _, _ = build_full_roleplay_profiles(progress_state)
        objective_summary = build_objective_summary(objective, scene_profile, persona_profile)
        planner_request = str((policy_state or {}).get("planner_request", "replan_policy") or "replan_policy")
        subset_catalog, subset_ids = _build_policy_catalog_subset(
            allowed_policy_ids=allowed_policy_ids,
            planner_request=planner_request,
            policy_state=policy_state,
            advisor_recs=advisor_recs,
            judge_result=judge_result,
        )
        catalog_json = _compact_policy_catalog_for_prompt(subset_catalog)
        meta["policy_subset_ids"] = subset_ids
        meta["policy_subset_chars"] = len(catalog_json)
        meta["policy_subset_size"] = len(subset_ids)
        messages = _planner_v2_prompt.format_messages(
            full_profiles_block=full_profiles_block,
            objective_summary=objective_summary,
            judge_result_json=json.dumps(judge_result or {}, ensure_ascii=False),
            advisor_recs_json=json.dumps(advisor_recs or {}, ensure_ascii=False),
            policy_catalog_es_subset_json=catalog_json,
            allowed_policy_ids_json=json.dumps(allowed_policy_ids, ensure_ascii=False),
            phase_definitions_es=PHASE_DEFINITIONS_ES,
            memory_short=memory_short,
            memory_long=memory_long,
            world_digest_json=json.dumps(build_world_digest(world_state, world_diff), ensure_ascii=False),
            world_full_json=json.dumps(world_state or {}, ensure_ascii=False),
            belief_digest_json=json.dumps(build_belief_digest(belief_state), ensure_ascii=False),
            belief_full_json=json.dumps(belief_state or {}, ensure_ascii=False),
            policy_state_json=json.dumps(policy_state or {}, ensure_ascii=False),
            phase_state_json=json.dumps(progress_state.get("phase_state", {}), ensure_ascii=False),
            active_plan_json=json.dumps(progress_state.get("active_plan", {}) or {}, ensure_ascii=False),
            progress_counters_json=json.dumps(progress_state.get("progress_counters", {}), ensure_ascii=False),
            plan_ledger_json=json.dumps(progress_state.get("plan_ledger", {}), ensure_ascii=False),
            judge_summary_json=json.dumps(judge_result or {}, ensure_ascii=False),
            reusable_policy_id=str((policy_state or {}).get("policy_id", "")),
            pivot_required_json=json.dumps({"pivot_required": bool(pivot_required)}, ensure_ascii=False),
            pivot_required_rules=(
                "PIVOT_REQUIRED=true: debes cambiar intent o modalidad (pregunta cerrada/control) y no repetir ask/intent previo."
                if pivot_required
                else "PIVOT_REQUIRED=false"
            ),
        )
        llm = get_planner_llm()
        structured = llm.with_structured_output(PlannerV2DecisionModel)
        meta["planner_input_payload_raw"] = [
            {"role": getattr(msg, "type", "user"), "content": str(getattr(msg, "content", ""))}
            for msg in messages
        ]
        meta["planner_input_prompt_rendered"] = "\n\n".join(
            f"[{item['role']}]\n{item['content']}" for item in meta["planner_input_payload_raw"]
        )

        retry_count = 0
        try:
            result = structured.invoke(messages)
        except Exception as exc:
            if not _is_length_parse_error(exc):
                raise
            retry_count = 1
            retry_tokens = max(1200, int(NEGOTIATION_CONFIG.planner.max_tokens or 1200) * 2)
            retry_llm = llm.bind(max_tokens=retry_tokens) if hasattr(llm, "bind") else llm
            retry_structured = retry_llm.with_structured_output(PlannerV2DecisionModel)
            retry_messages = [
                *messages,
                HumanMessage(content="Devuelve el JSON más compacto posible (2 steps), sin texto redundante."),
            ]
            meta["planner_retry_reason"] = "length_limit_or_truncated_json"
            meta["planner_retry_max_tokens"] = retry_tokens
            meta["planner_retry_instruction"] = "compact_json_2_steps"
            result = retry_structured.invoke(retry_messages)
            messages = retry_messages
        ended_wall = datetime.now(timezone.utc).isoformat()
        usage = extract_llm_usage(result)
        meta["planner_llm_called"] = True
        meta["planner_retry_count"] = retry_count
        payload = result.model_dump()
        meta["planner_output_payload_raw"] = payload
        meta["planner_output_text_rendered"] = json.dumps(payload, ensure_ascii=False)
        phase_candidate = {
            "phase": payload.get("phase", "climate"),
            "confidence": 0.7,
            "recovery_mode": bool(payload.get("recovery_mode", False)),
            "reasons": ["history:planner_v2"],
            "signals": [],
            "alternatives": [],
        }
        policy_decision = {
            "policy_id": str(payload.get("policy_id", "")),
            "reason": "planner_v2",
            "micro_goal": str(((payload.get("active_plan") or {}).get("steps") or [{}])[0].get("goal", "")),
            "risk_posture": "low",
            "why_short": "planner_v2",
            "inputs_used": [],
        }
        meta["active_plan"] = _to_active_plan(payload.get("active_plan") or {}, int(progress_state.get("last_progress_update_turn", 0) or 0) + 1)
        meta["executor_instruction"] = payload.get("executor_instruction") or {}
        normalized, issues = normalize_policy_decision(policy_decision, allowed_policy_ids)
        if issues:
            meta["policy_normalization_changed"] = True
            meta["issues"].extend(issues)
        if normalized.get("policy_id") not in allowed_policy_ids and allowed_policy_ids:
            normalized["policy_id"] = allowed_policy_ids[0]
            meta["policy_normalization_changed"] = True
        subset_policy_ids = list(meta.get("policy_subset_ids", []))
        if subset_policy_ids and normalized.get("policy_id") not in subset_policy_ids:
            fallback_policy_id = (
                "safe_neutral"
                if "safe_neutral" in subset_policy_ids
                else subset_policy_ids[0]
            )
            normalized["policy_id"] = fallback_policy_id
            meta["policy_normalization_changed"] = True
            meta.setdefault("issues", []).append("policy_not_in_subset_repaired")
        meta["planner_version"] = "v2"
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_start_ts"] = started_wall
        meta["planner_end_ts"] = ended_wall
        meta["planner_model"] = usage.get("model")
        meta["planner_tokens_in"] = usage.get("tokens_in")
        meta["planner_tokens_out"] = usage.get("tokens_out")
        meta["planner_queue_ms"] = usage.get("queue_ms")
        meta["planner_ttfb_ms"] = usage.get("ttfb_ms")
        meta["planner_finish_reason"] = usage.get("finish_reason")
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
