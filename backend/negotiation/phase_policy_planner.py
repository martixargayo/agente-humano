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


def _semantic_fallback() -> dict:
    return {
        "schema_version": "planner_semantic_v1",
        "phase": "clima_humano",
        "style": "Breve, natural y sin insistencia.",
        "next_move_hint": "RESPUESTA: Hola, gracias por escribir.\nMOVIMIENTO: Mantener tono cordial y avanzar sin repetir.\nTEMA: \"Pequeño rapport: día / cómo está\"",
        "what_not_to_repeat": [],
    }


def _extract_line_value(text: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{label}\s*:\s*(.+)$", text)
    return m.group(1).strip() if m else ""


_ALLOWED_NEED_INFO_SLOTS = {
    "saludo",
    "contexto",
    "precio_objetivo",
    "motivo_venta",
    "estado_general",
    "mantenimiento",
    "documentacion",
    "pago_fecha",
}

_TOPIC_TO_REQUIRED_SLOT = {
    "Motivo de venta (por qué ahora)": "motivo_venta",
    "Estado general hoy (en una frase)": "estado_general",
    "Mantenimiento y cuidados (qué se ha hecho)": "mantenimiento",
    "Cifra objetivo del vendedor (en qué cifra lo valora)": "precio_objetivo",
    "Checklist: forma y fecha de pago": "pago_fecha",
    "Checklist: entrega y trámites": "documentacion",
}

_INFO_INTENT_RE = re.compile(
    r"(?i)\b("
    r"preguntar|pregunta|saber|entender|explorar|profundizar|conocer|aclarar|"
    r"comprender|averiguar|confirmar|concretar|contextualizar|"
    r"indagar|consultar|pedir|solicitar|"
    r"me\s+gustar[ií]a|quisiera|necesito|ser[ií]a\s+[uú]til|"
    r"podr[ií]as"
    r")\b"
)

_INFO_INTENT_COMPOUND_RE = re.compile(
    r"(?i)("
    r"para\s+entender\s+mejor|para\s+poder|(?:para|a)\s+(entender|conocer|aclarar)|"
    r"que\s+me\s+(cuentes|digas|expliques)|"
    r"me\s+puedes\s+(decir|contar|explicar)|"
    r"podr[ií]as\s+((?:decir|contar|explicar)me|decirme|contarme|explicarme)"
    r")"
)


def _extract_need_info_slots(text: str) -> list[str]:
    m = re.search(r"(?im)^\s*NECESITA_INFO\s*:\s*(.+)$", text)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    slots = []
    for p in parts:
        s = re.sub(r"\s+", "_", p.strip().lower())
        s = s.strip("_")
        if s and s in _ALLOWED_NEED_INFO_SLOTS:
            slots.append(s)
    out = []
    for s in slots:
        if s not in out:
            out.append(s)
    return out[:2]


def _remove_questions_outside_tema(text: str) -> tuple[str, bool]:
    """
    Hard rule: forbid '?' and '¿' outside TEMA line.
    We only sanitize RESPUESTA/MOVIMIENTO/NECESITA_INFO lines.
    """
    changed = False
    lines = text.splitlines()
    new_lines = []
    for ln in lines:
        if re.search(r"(?im)^\s*TEMA\s*:", ln):
            new_lines.append(ln)
            continue
        ln2 = ln.replace("¿", "").replace("?", "")
        if ln2 != ln:
            changed = True
        new_lines.append(ln2)
    return "\n".join(new_lines), changed


def _looks_like_requesting_info_es(text: str) -> bool:
    text_norm = str(text or "")
    return bool(_INFO_INTENT_RE.search(text_norm) or _INFO_INTENT_COMPOUND_RE.search(text_norm))


def _normalize_next_move_hint(phase: str, hint: str) -> tuple[str, bool]:
    """
    Normaliza next_move_hint al contrato:
      RESPUESTA
      MOVIMIENTO
      TEMA
      (opcional) NECESITA_INFO
    y asegura que no haya '?' fuera de TEMA.
    """
    text = str(hint or "").strip()
    changed = False

    if not text:
        topic = default_topic_for_phase(phase)
        rebuilt = f'RESPUESTA: validar y avanzar sin preguntar.\nMOVIMIENTO: mantener tono y dar siguiente paso.\nTEMA: "{topic}"'
        return rebuilt, True

    if "\n" not in text:
        text2 = re.sub(r"\s+(MOVIMIENTO:|TEMA:|NECESITA_INFO:|PREGUNTA:)", r"\n\1", text, flags=re.IGNORECASE)
        if text2 != text:
            text = text2
            changed = True

    lines_wo_question = [ln for ln in text.splitlines() if not re.match(r"(?i)^\s*PREGUNTA\s*:", ln)]
    text_no_question = "\n".join(lines_wo_question)
    if text_no_question != text:
        text = text_no_question
        changed = True

    text, ch2 = _remove_questions_outside_tema(text)
    changed = changed or ch2

    response = _extract_line_value(text, "RESPUESTA")
    movement = _extract_line_value(text, "MOVIMIENTO")
    topic, _topic_src = extract_topic_selected(text)
    need_slots = _extract_need_info_slots(text)

    if not response:
        response = "validar y avanzar sin preguntar."
        changed = True
    if not movement:
        movement = "dar un siguiente paso concreto."
        changed = True

    if not topic or not is_valid_topic_for_phase(phase, topic):
        topic = default_topic_for_phase(phase)
        changed = True

    lines = [f"RESPUESTA: {response}", f"MOVIMIENTO: {movement}", f'TEMA: "{topic}"']
    if need_slots:
        lines.append("NECESITA_INFO: " + ", ".join(need_slots))
    rebuilt = "\n".join(lines)

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
        "planner_postcheck_requested_info_detected": False,
        "planner_postcheck_missing_necesita_info_retry": False,
        "planner_postcheck_forced_necesita_info": None,
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
        need_slots = _extract_need_info_slots(normalized_hint)
        response_line = _extract_line_value(normalized_hint, "RESPUESTA")
        movement_line = _extract_line_value(normalized_hint, "MOVIMIENTO")
        info_intent = _looks_like_requesting_info_es(f"{response_line} {movement_line}")
        meta["planner_postcheck_requested_info_detected"] = bool(info_intent)

        planner_retry_count = 0
        if info_intent and not need_slots:
            planner_retry_count = 1
            meta["planner_postcheck_missing_necesita_info_retry"] = True
            retry_user_prompt = user_prompt + "\n\nREINTENTO_CONTRATO: Falta NECESITA_INFO. Si necesitas datos, usa NECESITA_INFO: <slot>."
            retry_messages = [
                SystemMessage(content=PLANNER_SEMANTIC_V1_SYSTEM_PROMPT),
                HumanMessage(content=retry_user_prompt),
            ]
            retry_result = structured.invoke(retry_messages)
            payload = retry_result.model_dump()
            phase = str(payload.get("phase") or phase)
            normalized_hint, changed_retry = _normalize_next_move_hint(phase, payload.get("next_move_hint", ""))
            changed = changed or changed_retry
            need_slots = _extract_need_info_slots(normalized_hint)
            response_line = _extract_line_value(normalized_hint, "RESPUESTA")
            movement_line = _extract_line_value(normalized_hint, "MOVIMIENTO")
            info_intent = _looks_like_requesting_info_es(f"{response_line} {movement_line}")
            meta["planner_postcheck_requested_info_detected"] = bool(info_intent)

        if info_intent and not need_slots:
            # No "sanitizamos" con reemplazos raros: usamos fallback limpio y forzamos slot por topic.
            topic, _ = extract_topic_selected(normalized_hint)
            if not topic or not is_valid_topic_for_phase(phase, topic):
                topic = default_topic_for_phase(phase)

            forced_slot = _TOPIC_TO_REQUIRED_SLOT.get(topic)
            if forced_slot in _ALLOWED_NEED_INFO_SLOTS:
                need_slots = [forced_slot]
                meta["planner_postcheck_forced_necesita_info"] = forced_slot

            # Hint final minimalista y natural (sin verbos de pedir info)
            base_response = "validar y avanzar con tono colaborativo."
            base_movement = "dar un siguiente paso concreto."

            normalized_hint = "\n".join([
                f"RESPUESTA: {base_response}",
                f"MOVIMIENTO: {base_movement}",
                f'TEMA: "{topic}"',
                *( [f"NECESITA_INFO: {', '.join(need_slots)}"] if need_slots else [] ),
            ])
            changed = True

        payload["next_move_hint"] = normalized_hint
        meta["planner_postcheck_normalized"] = changed
        meta["planner_need_info_slots"] = need_slots
        meta["planner_retry_count"] = planner_retry_count

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
