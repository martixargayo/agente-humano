from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from .repo_prompts import (
    PLANNER_SEMANTIC_V1_SYSTEM_PROMPT,
    PLANNER_SEMANTIC_V1_USER_PROMPT,
)
from .elementos.strategy_definitions import PlannerSemanticV1DecisionModel
from .llm_clients import get_planner_llm
from .schemas import BeliefState, PolicyDecision, ProgressState, WorldState, default_policy_decision
from .phase_map import get_phase_map_v1
from .llm_planning_context import build_objective_summary, build_planner_context_block_full, build_full_roleplay_profiles
from .telemetry.llm_usage import extract_llm_usage
from .semantic_ledger_utils import build_effective_semantic_ledger, semantic_ledger_hash

logger = logging.getLogger(__name__)


def _semantic_fallback() -> dict:
    return {
        "schema_version": "planner_semantic_v1",
        "phase": "clima_humano",
        "style": "Breve, natural y sin insistencia.",
        "next_move_hint": "Responder de forma humana y continuar sin repetir temas ya tratados.",
        "what_not_to_repeat": [],
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
    user_message: str = "",
    assistant_last_message: str = "",
    effective_semantic_ledger: dict | None = None,
) -> tuple[dict, PolicyDecision, dict]:
    del world_state, world_diff, belief_state, policy_state, policy_plan_summary, constraints, constraints_struct
    del allowed_policy_ids

    meta = {
        "planner_llm_called": False,
        "planner_latency_ms": 0,
        "planner_failed": False,
        "planner_error": "",
        "planner_error_stage": "",
        "planner_fallback_used": False,
        "planner_version": "semantic_v1",
        "planner_input_prompt_rendered": "",
        "planner_input_payload_raw": None,
        "planner_output_text_rendered": "",
        "planner_output_payload_raw": None,
        "planner_semantic_output": None,
    }

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    try:
        semantic_ledger = (
            effective_semantic_ledger
            if isinstance(effective_semantic_ledger, dict)
            else build_effective_semantic_ledger(progress_state if isinstance(progress_state, dict) else {}, judge_result if isinstance(judge_result, dict) else {})
        )
        meta["planner_ledger_hash"] = semantic_ledger_hash(semantic_ledger)
        persona_profile, scene_profile, _style_contract, _constraints_struct = build_full_roleplay_profiles(progress_state)

        objective_source = "state"
        objective_summary = str(objective or "").strip()[:500]
        if not objective_summary:
            candidate = build_objective_summary(str(objective or ""), scene_profile, persona_profile).strip()[:500]
            if candidate:
                objective_summary = candidate
                objective_source = "builder"
        if not objective_summary:
            objective_summary = "Objetivo: avanzar con claridad y bajo riesgo en la negociación."[:500]
            objective_source = "default"

        memory_short_text = str(memory_short or "").strip()[:1200] or "SIN_MEMORIA_CORTA_AUN"
        memory_long_text = str(memory_long or "").strip()[:1200] or "SIN_RESUMEN_AUN"

        phase_map = get_phase_map_v1()
        full_profiles_block = build_planner_context_block_full(progress_state)

        user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(
            user_message=str(user_message or "")[:1000],
            assistant_last_message=str(assistant_last_message or "")[:1000],
            recent_history_text=str(recent_context or "")[-1200:],
            objective_summary=objective_summary,
            full_profiles_block=full_profiles_block,
            memory_short=memory_short_text,
            memory_long=memory_long_text,
            semantic_ledger_json=json.dumps(semantic_ledger or {}, ensure_ascii=False),
            phase_map_json=json.dumps(phase_map, ensure_ascii=False),
            advisor_recs_json=json.dumps(advisor_recs or {}, ensure_ascii=False),
        )
        meta["objective_source"] = objective_source
        meta["objective_summary"] = objective_summary
        meta["phase_map_json"] = phase_map
        messages = [
            SystemMessage(content=PLANNER_SEMANTIC_V1_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        llm = get_planner_llm()
        structured = llm.with_structured_output(PlannerSemanticV1DecisionModel)
        meta["planner_input_payload_raw"] = [
            {"role": getattr(msg, "type", "user"), "content": str(getattr(msg, "content", ""))}
            for msg in messages
        ]
        meta["planner_input_prompt_rendered"] = "\n\n".join(
            f"[{item['role']}]\n{item['content']}" for item in meta["planner_input_payload_raw"]
        )

        result = structured.invoke(messages)
        usage = extract_llm_usage(result)
        payload = result.model_dump()
        meta["planner_llm_called"] = True
        meta["planner_output_payload_raw"] = payload
        meta["planner_output_text_rendered"] = json.dumps(payload, ensure_ascii=False)
        meta["planner_semantic_output"] = payload
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_start_ts"] = started_wall
        meta["planner_end_ts"] = datetime.now(timezone.utc).isoformat()
        meta["planner_model"] = usage.get("model")
        meta["planner_tokens_in"] = usage.get("tokens_in")
        meta["planner_tokens_out"] = usage.get("tokens_out")

        phase_candidate = {
            "phase": payload.get("phase", "clima_humano"),
            "confidence": 0.7,
            "reasons": ["planner_semantic_v1"],
            "signals": [],
            "alternatives": [],
        }

        policy_decision: PolicyDecision = default_policy_decision()
        policy_decision["policy_id"] = "semantic_ledger"
        policy_decision["reason"] = "planner_semantic_v1"
        policy_decision["micro_goal"] = str(payload.get("next_move_hint", "") or "")[:140]
        policy_decision["why_short"] = str(payload.get("style", "") or "")[:140]
        policy_decision["inputs_used"] = ["semantic_ledger", "recent_context"]
        return phase_candidate, policy_decision, meta
    except Exception as exc:
        logger.warning("phase_policy_planner_semantic_error detail=%s", exc)
        payload = _semantic_fallback()
        meta["planner_llm_called"] = True
        meta["planner_failed"] = True
        meta["planner_fallback_used"] = True
        meta["planner_error"] = str(exc)
        meta["planner_error_stage"] = "llm_invoke"
        meta["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["planner_start_ts"] = started_wall
        meta["planner_end_ts"] = datetime.now(timezone.utc).isoformat()
        meta["planner_output_payload_raw"] = payload
        meta["planner_output_text_rendered"] = json.dumps(payload, ensure_ascii=False)
        meta["planner_semantic_output"] = payload

        phase_candidate = {
            "phase": payload.get("phase", "clima_humano"),
            "confidence": 0.4,
            "reasons": ["planner_semantic_fallback"],
            "signals": [],
            "alternatives": [],
        }
        policy_decision: PolicyDecision = default_policy_decision()
        policy_decision["policy_id"] = "semantic_ledger"
        policy_decision["reason"] = "planner_semantic_fallback"
        policy_decision["micro_goal"] = str(payload.get("next_move_hint", "") or "")[:140]
        policy_decision["why_short"] = "semantic_fallback"
        policy_decision["inputs_used"] = ["semantic_ledger"]
        return phase_candidate, policy_decision, meta
