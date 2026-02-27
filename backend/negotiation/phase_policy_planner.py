from __future__ import annotations

import json
import logging
import re
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
from .phase_cards_extended import OFFICIAL_PHASE_IDS, default_topic_for_phase, extract_topic_selected, is_valid_topic_for_phase
from .llm_planning_context import build_objective_summary, build_planner_context_block_full, build_full_roleplay_profiles
from .telemetry.llm_usage import extract_llm_usage
from .semantic_ledger_utils import build_effective_semantic_ledger, semantic_ledger_hash

logger = logging.getLogger(__name__)

_ALLOWED_OBJECTIVE_DELTAS = {"reduce_risk", "improve_price", "gain_commitment", "test_consistency", "move_to_close"}
_ALLOWED_TACTICS = {"frame", "anchor", "conditional_offer", "tradeoff", "boundary", "silence"}


def _semantic_fallback() -> dict:
    return {
        "schema_version": "planner_semantic_v1",
        "phase": "clima_humano",
        "style": "Breve, natural y sin insistencia.",
        "next_move_hint": (
            "OBJECTIVE_DELTA: reduce_risk\n"
            "TACTIC: frame\n"
            "RESPUESTA: validar y avanzar con tono colaborativo.\n"
            "MOVIMIENTO: dar un siguiente paso concreto.\n"
            'TEMA: "Pequeño rapport: día / cómo está"'
        ),
        "what_not_to_repeat": [],
    }


def _extract_line_value(text: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{label}\s*:\s*(.+)$", str(text or ""))
    return m.group(1).strip() if m else ""


def _remove_questions_outside_tema(text: str) -> tuple[str, bool]:
    changed = False
    lines = str(text or "").splitlines()
    new_lines: list[str] = []
    for ln in lines:
        if re.search(r"(?im)^\s*TEMA\s*:", ln):
            new_lines.append(ln)
            continue
        ln2 = ln.replace("¿", "").replace("?", "")
        if ln2 != ln:
            changed = True
        new_lines.append(ln2)
    return "\n".join(new_lines), changed


def _normalize_next_move_hint(phase: str, hint: str) -> tuple[str, bool]:
    text = str(hint or "").strip()
    changed = False

    if not text:
        topic = default_topic_for_phase(phase)
        rebuilt = (
            "OBJECTIVE_DELTA: reduce_risk\n"
            "TACTIC: frame\n"
            "RESPUESTA: validar y avanzar con tono colaborativo.\n"
            "MOVIMIENTO: dar un siguiente paso concreto.\n"
            f'TEMA: "{topic}"'
        )
        return rebuilt, True

    if "\n" not in text:
        text2 = re.sub(r"\s+(TACTIC:|RESPUESTA:|MOVIMIENTO:|TEMA:|OBJECTIVE_DELTA:|PREGUNTA:)", r"\n\1", text, flags=re.IGNORECASE)
        if text2 != text:
            text = text2
            changed = True

    lines_wo_pregunta = [ln for ln in text.splitlines() if not re.match(r"(?i)^\s*PREGUNTA\s*:", ln)]
    text_no_pregunta = "\n".join(lines_wo_pregunta)
    if text_no_pregunta != text:
        text = text_no_pregunta
        changed = True

    text, ch2 = _remove_questions_outside_tema(text)
    changed = changed or ch2

    objective_delta = _extract_line_value(text, "OBJECTIVE_DELTA").lower().strip()
    tactic = _extract_line_value(text, "TACTIC").lower().strip()
    response = _extract_line_value(text, "RESPUESTA")
    movement = _extract_line_value(text, "MOVIMIENTO")
    topic, _topic_src = extract_topic_selected(text)

    if objective_delta not in _ALLOWED_OBJECTIVE_DELTAS:
        objective_delta = "reduce_risk"
        changed = True
    if tactic not in _ALLOWED_TACTICS:
        tactic = "frame"
        changed = True
    if not response:
        response = "validar y avanzar con tono colaborativo."
        changed = True
    if not movement:
        movement = "dar un siguiente paso concreto."
        changed = True
    if not topic or not is_valid_topic_for_phase(phase, topic):
        topic = default_topic_for_phase(phase)
        changed = True

    rebuilt = "\n".join([
        f"OBJECTIVE_DELTA: {objective_delta}",
        f"TACTIC: {tactic}",
        f"RESPUESTA: {response}",
        f"MOVIMIENTO: {movement}",
        f'TEMA: "{topic}"',
    ])

    if rebuilt != text:
        changed = True

    return rebuilt, changed


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
    del allowed_policy_ids, advisor_recs

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
        "planner_postcheck_normalized": False,
        "planner_objective_delta": "reduce_risk",
        "planner_tactic": "frame",
        "planner_hint_contract_ok": False,
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

        phase_map = get_phase_map_v1()
        full_profiles_block = build_planner_context_block_full(progress_state)
        del full_profiles_block, memory_short, memory_long

        prev_phase = str((((progress_state or {}).get("phase_state") or {}).get("phase") or "clima_humano"))
        allowed_next_phases = [p for p in phase_map.keys() if p in OFFICIAL_PHASE_IDS] or OFFICIAL_PHASE_IDS
        style_id = str(((_style_contract or {}).get("style_id") or "psyplay_compact"))
        lo_que_ya_se_toco = list((semantic_ledger or {}).get("lo_que_ya_se_toco", [])) if isinstance(semantic_ledger, dict) else []
        lo_que_ya_pregunte = list((semantic_ledger or {}).get("lo_que_ya_pregunte", [])) if isinstance(semantic_ledger, dict) else []
        lo_que_falta_pero_no_insistire = list((semantic_ledger or {}).get("lo_que_falta_pero_no_insistire", [])) if isinstance(semantic_ledger, dict) else []

        user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(
            speaker="seller",
            user_message=str(user_message or "")[:1000],
            assistant_last_message=str(assistant_last_message or "")[:1000],
            style_id=style_id,
            max_words=int((_constraints_struct or {}).get("max_words", 30) or 30),
            max_questions=int((_constraints_struct or {}).get("max_questions", 1) or 1),
            prev_phase=prev_phase,
            allowed_next_phases_json=json.dumps(allowed_next_phases, ensure_ascii=False),
            lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
            lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
            lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
            recent_history_compact=str(recent_context or "")[-1200:],
            objective_summary_compact=objective_summary,
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
        phase = str(payload.get("phase") or "clima_humano")
        normalized_hint, changed = _normalize_next_move_hint(phase, payload.get("next_move_hint", ""))
        objective_delta = _extract_line_value(normalized_hint, "OBJECTIVE_DELTA").lower().strip() or "reduce_risk"
        tactic = _extract_line_value(normalized_hint, "TACTIC").lower().strip() or "frame"

        payload["next_move_hint"] = normalized_hint
        meta["planner_postcheck_normalized"] = changed
        meta["planner_retry_count"] = 0
        meta["planner_objective_delta"] = objective_delta
        meta["planner_tactic"] = tactic
        meta["planner_hint_contract_ok"] = all(
            bool(_extract_line_value(normalized_hint, label))
            for label in ["OBJECTIVE_DELTA", "TACTIC", "RESPUESTA", "MOVIMIENTO", "TEMA"]
        )

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
        meta["planner_objective_delta"] = "reduce_risk"
        meta["planner_tactic"] = "frame"

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
