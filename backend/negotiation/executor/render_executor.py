from __future__ import annotations

import json
import os
import re
from copy import deepcopy

from langchain_core.messages import HumanMessage, SystemMessage

from ..elementos.render.executor_prompts import (
    EXECUTOR_OUTPUT_SCHEMA,
    EXECUTOR_SYSTEM_PROMPT,
    EXECUTOR_USER_PROMPT,
)
from ..phase_map import get_phase_map_v1
from ..phase_cards_extended import get_phase_card_extended, extract_topic_selected, default_topic_for_phase, is_valid_topic_for_phase
from ..semantic_ledger_utils import semantic_ledger_hash

ExecutorOutput = dict
RenderConstraints = dict

_WORD_CAP_LIMIT = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP", "40") or 40)
_WORD_CAP_MAX_RERUNS = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP_MAX_RERUNS", "1") or 1)
_WORD_CAP_RETRY_INSTRUCTION = (
    f"REINTENTO_BREVEDAD: Devuelve JSON válido y limita response_text a máximo {_WORD_CAP_LIMIT} palabras."
)
_PROMPT_SWAP_V2_ENABLED = str(os.getenv("NEGOTIATION_PROMPT_SWAP_V2_ENABLED", "1") or "1").strip().lower() in {"1","true","yes","on"}
_TEXT_ONLY_FORBIDDEN_RE = re.compile(r"\b(muéstrame|muestrame|enséñame|ensename|envíame|enviame|adjunta|pásame|pasame|tráeme|traeme)\b", re.IGNORECASE)


def _word_count(text: str) -> int:
    return len(str(text or "").split())


def _truncate_words(text: str, limit: int) -> str:
    words = str(text or "").split()
    if len(words) <= limit:
        return str(text or "").strip()
    return " ".join(words[:limit]).strip()


def _with_word_cap_instruction(prompt: str) -> str:
    prompt_text = str(prompt or "").rstrip()
    if _WORD_CAP_RETRY_INSTRUCTION in prompt_text:
        return prompt_text
    return f"{prompt_text}\n\n{_WORD_CAP_RETRY_INSTRUCTION}"


def _safe_neutral_fallback() -> str:
    return "Puedo ayudarte, pero necesito un poco más de contexto para responder bien."


def safe_json_load(raw: object) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_executor_output(raw: object) -> ExecutorOutput:
    base: ExecutorOutput = {
        "schema_version": "executor_v2",
        "response_text": "",
        "asked_question": False,
        "requested_info_slots": [],
        "tone_used": "neutral",
        "followup_intent": None,
        "render_meta": {},
    }
    if not isinstance(raw, dict):
        base["response_text"] = _safe_neutral_fallback()
        return base

    response_text = str(raw.get("response_text", "")).strip() or _safe_neutral_fallback()
    asked_question = bool(raw.get("asked_question", False))
    requested = raw.get("requested_info_slots") if isinstance(raw.get("requested_info_slots"), list) else []
    requested = [str(x).strip()[:40] for x in requested if str(x).strip()][:4]

    out = dict(base)
    out["schema_version"] = "executor_v2"
    out["response_text"] = response_text
    out["asked_question"] = asked_question
    out["requested_info_slots"] = requested
    out["tone_used"] = str(raw.get("tone_used", "neutral") or "neutral")
    out["followup_intent"] = raw.get("followup_intent")
    out["render_meta"] = raw.get("render_meta") if isinstance(raw.get("render_meta"), dict) else {}
    return out


def _enforce_executor_v2_contract(out: dict, style: dict, constraints: dict) -> dict:
    data = normalize_executor_output(out)
    max_words = int((style or {}).get("max_words") or _WORD_CAP_LIMIT)
    if _word_count(data["response_text"]) > max_words:
        data["response_text"] = _truncate_words(data["response_text"], max_words)
    max_questions = int((style or {}).get("max_questions") or (constraints or {}).get("max_questions") or 1)
    if max_questions < 0:
        max_questions = 0
    if data["response_text"].count("?") > max_questions:
        parts = data["response_text"].split("?")
        data["response_text"] = "?".join(parts[: max_questions + 1]).strip()
        if max_questions > 0 and not data["response_text"].endswith("?"):
            data["response_text"] = data["response_text"].rstrip(" .") + "?"

    asked_question = bool(data.get("asked_question", False))
    requested_slots = data.get("requested_info_slots") if isinstance(data.get("requested_info_slots"), list) else []
    if asked_question and not requested_slots:
        data["requested_info_slots"] = ["clarify_context"]
    return data




def _count_text_only_violations(text: str) -> int:
    return len(_TEXT_ONLY_FORBIDDEN_RE.findall(str(text or "")))


def _build_retry_hint_for_text_only() -> str:
    return "REINTENTO_CANAL: reformula 100% a texto; no uses verbos mostrar/enviar/adjuntar."

def extract_last_counterparty_utterance(state: dict) -> str:
    recent_history_text = str(state.get("recent_history_text", "") or "").strip()
    if recent_history_text:
        for line in reversed([ln.strip() for ln in recent_history_text.splitlines() if ln.strip()]):
            lowered = line.lower()
            if lowered.startswith("vendedor:") or lowered.startswith("don joaquín:"):
                return line
    return str(state.get("user_message", "") or "").strip()


def render_executor_output(
    state: dict,
    *,
    deps,
    conversation_mode: str,
    policy_pack_active: str,
    policy_id: str,
    persona_profile: dict,
    scene_profile: dict,
    style_contract: dict,
    constraints_struct: RenderConstraints,
    strategy_summary: dict,
    memory_block: str,
    world_state: dict,
    user_message: str,
) -> ExecutorOutput:
    del conversation_mode, policy_pack_active, policy_id, strategy_summary, memory_block
    persona = deepcopy(persona_profile)
    scene = deepcopy(scene_profile)
    style = deepcopy(style_contract)
    constraints = deepcopy(constraints_struct)

    planner_semantic_output = state.get("planner_semantic_output") if isinstance(state.get("planner_semantic_output"), dict) else {}
    semantic_ledger = state.get("effective_semantic_ledger") if isinstance(state.get("effective_semantic_ledger"), dict) else ((state.get("progress_state") or {}).get("semantic_ledger") if isinstance(state.get("progress_state"), dict) else {})
    state["executor_ledger_hash"] = semantic_ledger_hash(semantic_ledger if isinstance(semantic_ledger, dict) else {})
    assistant_last_message_ctx = str(state.get("assistant_last_message") or state.get("last_assistant_message") or "")

    phase_id = str((planner_semantic_output or {}).get("phase") or "clima_humano")
    next_move_hint = str((planner_semantic_output or {}).get("next_move_hint") or "")
    topic_selected, topic_source = extract_topic_selected(next_move_hint)
    if not topic_selected:
        topic_selected = default_topic_for_phase(phase_id)
        topic_source = "phase_default" if topic_selected != "sin_tema" else "none"
    elif not is_valid_topic_for_phase(phase_id, topic_selected):
        topic_selected = default_topic_for_phase(phase_id)
        topic_source = "invalid_fallback" if topic_selected != "sin_tema" else "none"
    phase_card, phase_card_lookup_status = get_phase_card_extended(phase_id)

    lo_que_ya_se_toco = list((semantic_ledger or {}).get("lo_que_ya_se_toco", [])) if isinstance(semantic_ledger, dict) else []
    lo_que_ya_pregunte = list((semantic_ledger or {}).get("lo_que_ya_pregunte", [])) if isinstance(semantic_ledger, dict) else []
    lo_que_falta_pero_no_insistire = list((semantic_ledger or {}).get("lo_que_falta_pero_no_insistire", [])) if isinstance(semantic_ledger, dict) else []

    prompt = EXECUTOR_USER_PROMPT.format(
        speaker=str(state.get("speaker_of_user_message") or "seller").strip().lower(),
        user_message=user_message,
        last_seller_utterance=extract_last_counterparty_utterance(state),
        assistant_last_message=assistant_last_message_ctx,
        profile_card_compact_text=json.dumps(persona, ensure_ascii=False),
        scene_card_compact_text=json.dumps(scene, ensure_ascii=False),
        style_id=str(style.get("style_id", "psyplay_compact")),
        max_words=int(style.get("max_words", _WORD_CAP_LIMIT) or _WORD_CAP_LIMIT),
        max_questions=int(style.get("max_questions", constraints.get("max_questions", 1)) or 1),
        planner_semantic_output_json=json.dumps(planner_semantic_output, ensure_ascii=False),
        phase=phase_card.get("phase", phase_id),
        phase_do_short=phase_card.get("do", ""),
        phase_avoid_short=phase_card.get("avoid", ""),
        phase_question_policy=phase_card.get("question_policy", ""),
        topic_selected=topic_selected,
        lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
        lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
        lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
        recent_history_compact=str(state.get("recent_history_text", "") or "").strip()[-1200:] or "SIN_MEMORIA_CORTA_AUN",
        memory_long_compact=str(state.get("long_memory", "") or "").strip() or "SIN_RESUMEN_AUN",
        retry_hint="",
    )
    state["topic_selected"] = topic_selected
    state["topic_selected_source"] = topic_source
    state["phase_card_lookup_status"] = phase_card_lookup_status

    messages = [
        SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
        HumanMessage(content=prompt.strip()),
    ]

    raw = deps.execute(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = safe_json_load(text)
    out = normalize_executor_output(data)

    original_words = _word_count(str((data or {}).get("response_text", "")))
    reruns = 0
    text_only_violations_count = _count_text_only_violations(out.get("response_text", ""))
    fallback_truncate = False
    retry_prompt = _with_word_cap_instruction(prompt)

    needs_retry = (_word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT) or (_PROMPT_SWAP_V2_ENABLED and text_only_violations_count > 0)
    while needs_retry and reruns < _WORD_CAP_MAX_RERUNS + 1:
        reruns += 1
        extra_hint = _build_retry_hint_for_text_only() if text_only_violations_count > 0 else ""
        retry_messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=(retry_prompt + "\n\n" + extra_hint).strip()),
        ]
        retry_raw = deps.execute(retry_messages)
        retry_text = retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", "")
        out = normalize_executor_output(safe_json_load(retry_text))
        text_only_violations_count = _count_text_only_violations(out.get("response_text", ""))
        needs_retry = (_word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT) or (_PROMPT_SWAP_V2_ENABLED and text_only_violations_count > 0)

    if _word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT:
        fallback_truncate = True
        out = dict(out)
        out["response_text"] = _truncate_words(str(out.get("response_text", "")), _WORD_CAP_LIMIT)

    render_meta = dict(out.get("render_meta") or {}) if isinstance(out.get("render_meta"), dict) else {}
    render_meta["word_cap_limit"] = _WORD_CAP_LIMIT
    render_meta["word_cap_original_words"] = original_words
    render_meta["word_cap_reruns"] = reruns
    render_meta["word_cap_fallback_truncate"] = fallback_truncate
    render_meta["executor_retry_count"] = reruns
    render_meta["text_only_violations_count"] = text_only_violations_count
    render_meta["topic_selected"] = state.get("topic_selected", "")
    render_meta["topic_selected_source"] = state.get("topic_selected_source", "none")
    render_meta["phase_card_lookup_status"] = state.get("phase_card_lookup_status", "missing")
    out["render_meta"] = render_meta

    return _enforce_executor_v2_contract(normalize_executor_output(out), style, constraints)
