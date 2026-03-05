from __future__ import annotations

import json
import os
import re
from copy import deepcopy

from langchain_core.messages import HumanMessage, SystemMessage

from ..elementos.render.executor_prompts import (
    EXECUTOR_SYSTEM_PROMPT,
    EXECUTOR_USER_PROMPT,
)
from ..phase_cards_extended import get_phase_card_extended, extract_topic_selected, default_topic_for_phase, is_valid_topic_for_phase
from ..semantic_ledger_utils import semantic_ledger_hash
from ..negotiation_profiles import NEGOTIATION_PROFILE_PRIVATE_EXECUTOR_V1

ExecutorOutput = dict
RenderConstraints = dict

_WORD_CAP_LIMIT = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP", "40") or 40)
_WORD_CAP_MAX_RERUNS = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP_MAX_RERUNS", "1") or 1)
_WORD_CAP_RETRY_INSTRUCTION = f"REINTENTO_BREVEDAD: Devuelve JSON válido y limita response_text a máximo {_WORD_CAP_LIMIT} palabras."
_SCHEMA_RETRY_INSTRUCTION = "REINTENTO_ESQUEMA: Devuelve SOLO JSON executor_v2 con schema_version y response_text. Sin otras claves."
_PROMPT_SWAP_V2_ENABLED = str(os.getenv("NEGOTIATION_PROMPT_SWAP_V2_ENABLED", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
_TEXT_ONLY_FORBIDDEN_RE = re.compile(r"\b(muéstrame|muestrame|enséñame|ensename|envíame|enviame|adjunta|pásame|pasame|tráeme|traeme)\b", re.IGNORECASE)
_PRECIO_CIFRA_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\ben qu[eé] cifra\b",
        r"\bcu[aá]nto\s+(pides|ser[ií]a|quieres|aceptas)\b",
        r"\bpor cu[aá]nto\b",
        r"\bqu[eé]\s+precio\b",
        r"\bte\s+encaja\s+\d",
        r"\bprecio\s+final\b",
        r"\bcifra\b",
    )
]
def _word_count(text: str) -> int:
    return len(str(text or "").split())


def _truncate_words(text: str, limit: int) -> str:
    words = str(text or "").split()
    if len(words) <= limit:
        return str(text or "").strip()
    return " ".join(words[:limit]).strip()


def _safe_neutral_fallback() -> str:
    return "Puedo ayudarte, pero necesito un poco más de contexto para responder bien."


def _with_retry_instruction(prompt: str, instruction: str) -> str:
    prompt_text = str(prompt or "").rstrip()
    if instruction in prompt_text:
        return prompt_text
    return f"{prompt_text}\n\n{instruction}"


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


def _is_valid_executor_v2_payload(data: dict) -> bool:
    return isinstance(data, dict) and str(data.get("schema_version") or "") == "executor_v2" and bool(str(data.get("response_text") or "").strip())


def _salvage_response_text(data: dict) -> tuple[dict, bool]:
    if not isinstance(data, dict):
        return {}, False
    if not data.get("response_text") and isinstance(data.get("response"), str) and data.get("response").strip():
        patched = dict(data)
        patched["response_text"] = str(data.get("response")).strip()
        if not patched.get("schema_version"):
            patched["schema_version"] = "executor_v2"
        return patched, True
    return data, False


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


def _enforce_executor_v2_contract(
    out: dict,
    style: dict,
    constraints: dict,
    *,
    question_allowed: bool = True,
) -> dict:
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

    asked_question = detect_question_from_text(data["response_text"])

    requested_slots = data.get("requested_info_slots") if isinstance(data.get("requested_info_slots"), list) else []
    requested_slots = [str(x).strip()[:32] for x in requested_slots if str(x).strip()][:3]

    if question_allowed is False:
        data["asked_question"] = False
        data["requested_info_slots"] = []
        if _looks_like_question_es(data["response_text"]):
            cleaned = _remove_interrogative_sentences_es(str(data["response_text"]))
            data["response_text"] = cleaned or _safe_neutral_fallback()
            meta = dict(data.get("render_meta") or {}) if isinstance(data.get("render_meta"), dict) else {}
            meta["question_forced_removed"] = True
            data["render_meta"] = meta
        return data

    if asked_question:
        data["requested_info_slots"] = map_slots_from_questions(data["response_text"]) or requested_slots[:3]
    else:
        data["requested_info_slots"] = []

    data["asked_question"] = asked_question

    if not question_allowed:
        data["asked_question"] = False
        data["requested_info_slots"] = []
        if "?" in data["response_text"] or "¿" in data["response_text"]:
            cleaned = str(data["response_text"]).replace("¿", "")
            if "?" in cleaned:
                cleaned = cleaned.split("?", 1)[0]
            cleaned = cleaned.strip().rstrip(".,;:")
            data["response_text"] = cleaned or _safe_neutral_fallback()
            meta = dict(data.get("render_meta") or {}) if isinstance(data.get("render_meta"), dict) else {}
            meta["question_forced_removed"] = True
            data["render_meta"] = meta
    return data


def _count_text_only_violations(text: str) -> int:
    return len(_TEXT_ONLY_FORBIDDEN_RE.findall(str(text or "")))


def _build_retry_hint_for_text_only() -> str:
    return "REINTENTO_CANAL: reformula 100% a texto; no uses verbos mostrar/enviar/adjuntar."


def _extract_plan_marker(text: str, marker: str) -> str:
    m = re.search(rf"(?im)^\s*{marker}\s*:\s*(.+)$", str(text or ""))
    return m.group(1).strip() if m else ""


def _extract_objective_delta_and_tactic(next_move_hint: str) -> tuple[str, str]:
    objective_delta = _extract_plan_marker(next_move_hint, "OBJECTIVE_DELTA").lower().strip()
    tactic = _extract_plan_marker(next_move_hint, "TACTIC").lower().strip()
    if objective_delta not in {"reduce_risk", "improve_price", "gain_commitment", "test_consistency", "move_to_close"}:
        objective_delta = "reduce_risk"
    if tactic not in {"frame", "anchor", "conditional_offer", "tradeoff", "boundary", "silence"}:
        tactic = "frame"
    return objective_delta, tactic


def _user_asked_direct_question(msg: str) -> bool:
    return _looks_like_question_es(msg)


def detect_question_from_text(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    start = t.find("¿")
    end = t.find("?", start + 1 if start >= 0 else 0)
    return start >= 0 and end > start


def _looks_like_question_es(text: str) -> bool:
    return detect_question_from_text(text)


def _remove_interrogative_sentences_es(text: str) -> str:
    chunks = re.split(r"(?<=[.!])\s+", str(text or "").strip())
    kept = [chunk.strip() for chunk in chunks if chunk.strip() and not _looks_like_question_es(chunk)]
    return " ".join(kept).strip()


def _compact_profile_card(persona: dict) -> str:
    if not isinstance(persona, dict):
        return "comprador prudente, respetuoso y orientado a cierre claro"
    name = str(persona.get("name") or "Carlos")
    traits = [
        str(persona.get("role") or "comprador"),
        "prudente",
        "relacional",
    ]
    hard = "no revelar BATNA/presupuesto máximo, evitar presión"
    return f"{name}: {', '.join(traits)}. Hard limits: {hard}."


def _compact_scene_card(scene: dict) -> str:
    if not isinstance(scene, dict):
        return "primera conversación comprador-vendedor; canal solo texto"
    counterpart = str(scene.get("counterparty") or "vendedor")
    setting = str(scene.get("setting") or "negociación por chat")
    return f"Escena: {setting}. Interlocutor: {counterpart}. Canal: solo texto."




def extract_questions_spans(text: str) -> list[str]:
    spans: list[str] = []
    src = str(text or "")
    cursor = 0
    while True:
        start = src.find("¿", cursor)
        if start < 0:
            break
        end = src.find("?", start + 1)
        if end < 0:
            break
        spans.append(src[start + 1 : end].strip())
        cursor = end + 1
    return [s for s in spans if s]


def map_slots_from_questions(text: str) -> list[str]:
    if not detect_question_from_text(text):
        return []
    questions = extract_questions_spans(text)
    if not questions:
        return []
    joined = " ".join(questions).lower()
    slots: list[str] = []
    if any(p.search(joined) for p in _PRECIO_CIFRA_PATTERNS):
        slots.append("precio_objetivo")
    if any(x in joined for x in ("motivo", "por qué vendes", "razón de venta")):
        slots.append("motivo_venta")
    if any(x in joined for x in ("estado", "cómo está", "como está")):
        slots.append("estado_general")
    if any(x in joined for x in ("mantenimiento", "revisión", "revision", "itv")):
        slots.append("mantenimiento")
    if any(x in joined for x in ("papeles", "documentación", "documentacion", "transferencia")):
        slots.append("documentacion")
    if any(x in joined for x in ("pago", "fecha", "cuándo", "cuando", "señal")):
        slots.append("pago_fecha")
    if not slots:
        slots.append("contexto")
    return slots[:3]

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
    del conversation_mode, policy_pack_active, policy_id, strategy_summary, memory_block, world_state
    persona = deepcopy(persona_profile)
    scene = deepcopy(scene_profile)
    style = deepcopy(style_contract)
    constraints = deepcopy(constraints_struct)

    planner_semantic_output = state.get("planner_semantic_output") if isinstance(state.get("planner_semantic_output"), dict) else {}
    semantic_ledger = state.get("effective_semantic_ledger") if isinstance(state.get("effective_semantic_ledger"), dict) else ((state.get("progress_state") or {}).get("semantic_ledger") if isinstance(state.get("progress_state"), dict) else {})
    state["executor_ledger_hash"] = semantic_ledger_hash(semantic_ledger if isinstance(semantic_ledger, dict) else {})
    assistant_last_message_ctx = str(state.get("assistant_last_message") or state.get("last_assistant_message") or "")

    phase_id = str((planner_semantic_output or {}).get("phase") or "clima_humano")
    prev_phase = str((((state.get("progress_state") or {}).get("phase_state") or {}).get("phase")) or "clima_humano")
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
    objective_delta, tactic = _extract_objective_delta_and_tactic(next_move_hint)

    progress_state = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else {}
    memory_short_raw = str(state.get("short_memory") or "").strip()
    if memory_short_raw:
        recent_history_compact = memory_short_raw
        memory_short_source = "progress_state"
    elif ("memory_short" in progress_state) or ("turn_buffer" in progress_state):
        recent_history_compact = "SIN_MEMORIA_CORTA_AUN"
        memory_short_source = "progress_state"
    elif str(state.get("recent_history_text", "") or "").strip():
        recent_history_compact = str(state.get("recent_history_text", "") or "").strip()
        memory_short_source = "legacy_recent_history"
    else:
        recent_history_compact = "SIN_MEMORIA_CORTA_AUN"
        memory_short_source = "fallback_build_memory_context"

    memory_long_compact = str(state.get("long_memory", "") or "").strip() or "SIN_RESUMEN_AUN"
    memory_short_turns_rendered = sum(1 for line in recent_history_compact.splitlines() if line.startswith("user:"))
    long_turns_summarized = int(progress_state.get("memory_long_turns_summarized") or 0)
    memory_short_last_turn_idx = (long_turns_summarized + memory_short_turns_rendered) if memory_short_turns_rendered > 0 else None

    prompt = EXECUTOR_USER_PROMPT.format(
        speaker=str(state.get("speaker_of_user_message") or "seller").strip().lower(),
        user_message=user_message,
        last_seller_utterance=extract_last_counterparty_utterance(state),
        assistant_last_message=assistant_last_message_ctx,
        profile_card_compact_text=_compact_profile_card(persona),
        scene_card_compact_text=_compact_scene_card(scene),
        style_id=str(style.get("style_id", "psyplay_compact")),
        max_words=int(style.get("max_words", _WORD_CAP_LIMIT) or _WORD_CAP_LIMIT),
        max_questions=int(style.get("max_questions", constraints.get("max_questions", 1)) or 1),
        planner_semantic_output_json=json.dumps(planner_semantic_output, ensure_ascii=False),
        prev_phase=prev_phase,
        phase=phase_card.get("phase", phase_id),
        objective_delta=objective_delta,
        tactic=tactic,
        phase_question_policy=phase_card.get("question_policy", ""),
        topic_selected=topic_selected,
        lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
        lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
        lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
        recent_history_compact=recent_history_compact,
        memory_long_compact=memory_long_compact,
        negotiation_profile_private_executor=str(NEGOTIATION_PROFILE_PRIVATE_EXECUTOR_V1 or ""),
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
    llm_raw_output_text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = safe_json_load(llm_raw_output_text)
    data, schema_salvage = _salvage_response_text(data)
    llm_parsed_output = dict(data) if isinstance(data, dict) else {}

    schema_retry_count = 0
    if not _is_valid_executor_v2_payload(data):
        schema_retry_count = 1
        schema_retry_prompt = _with_retry_instruction(prompt, _SCHEMA_RETRY_INSTRUCTION)
        retry_messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=schema_retry_prompt.strip()),
        ]
        retry_raw = deps.execute(retry_messages)
        llm_raw_output_text = retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", "")
        retry_data = safe_json_load(llm_raw_output_text)
        retry_data, schema_salvage_retry = _salvage_response_text(retry_data)
        schema_salvage = schema_salvage or schema_salvage_retry
        data = retry_data
        llm_parsed_output = dict(data) if isinstance(data, dict) else {}

    out = normalize_executor_output(data)
    original_words = _word_count(str(out.get("response_text", "")))

    question_allowed = True
    interrogative_retry_count = 0
    if _looks_like_question_es(str(out.get("response_text", ""))) and (not question_allowed):
        interrogative_retry_count = 1
        retry_hint_q = "RETRY_HINT: No hagas preguntas ni frases interrogativas. Responde declarativamente y devuelve SOLO JSON executor_v2."
        retry_prompt_q = _with_retry_instruction(prompt, retry_hint_q)
        retry_messages_q = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=retry_prompt_q.strip()),
        ]
        retry_raw_q = deps.execute(retry_messages_q)
        llm_raw_output_text = retry_raw_q if isinstance(retry_raw_q, str) else getattr(retry_raw_q, "content", "")
        retry_data_q = safe_json_load(llm_raw_output_text)
        retry_data_q, schema_salvage_retry = _salvage_response_text(retry_data_q)
        schema_salvage = schema_salvage or schema_salvage_retry
        llm_parsed_output = dict(retry_data_q) if isinstance(retry_data_q, dict) else {}
        out = normalize_executor_output(retry_data_q)

    question_forced_removed = False
    if _looks_like_question_es(str(out.get("response_text", ""))) and (not question_allowed):
        question_forced_removed = True
        cleaned = _remove_interrogative_sentences_es(str(out.get("response_text", "")))
        out = dict(out)
        out["response_text"] = cleaned or _safe_neutral_fallback()
        out["asked_question"] = False
        out["requested_info_slots"] = []

    text_retry_count = 0
    text_only_violations_count = _count_text_only_violations(out.get("response_text", ""))
    fallback_truncate = False
    needs_retry = (_word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT) or (_PROMPT_SWAP_V2_ENABLED and text_only_violations_count > 0)
    retry_prompt = _with_retry_instruction(prompt, _WORD_CAP_RETRY_INSTRUCTION)

    while needs_retry and text_retry_count < _WORD_CAP_MAX_RERUNS + 1:
        text_retry_count += 1
        extra_hint = _build_retry_hint_for_text_only() if text_only_violations_count > 0 else ""
        retry_messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=(retry_prompt + "\n\n" + extra_hint).strip()),
        ]
        retry_raw = deps.execute(retry_messages)
        llm_raw_output_text = retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", "")
        retry_data = safe_json_load(llm_raw_output_text)
        retry_data, schema_salvage_retry = _salvage_response_text(retry_data)
        schema_salvage = schema_salvage or schema_salvage_retry
        llm_parsed_output = dict(retry_data) if isinstance(retry_data, dict) else {}
        out = normalize_executor_output(retry_data)
        text_only_violations_count = _count_text_only_violations(out.get("response_text", ""))
        needs_retry = (_word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT) or (_PROMPT_SWAP_V2_ENABLED and text_only_violations_count > 0)

    if _word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT:
        fallback_truncate = True
        out = dict(out)
        out["response_text"] = _truncate_words(str(out.get("response_text", "")), _WORD_CAP_LIMIT)

    total_retry_count = schema_retry_count + interrogative_retry_count + text_retry_count
    render_meta = dict(out.get("render_meta") or {}) if isinstance(out.get("render_meta"), dict) else {}
    render_meta["word_cap_limit"] = _WORD_CAP_LIMIT
    render_meta["word_cap_original_words"] = original_words
    render_meta["word_cap_reruns"] = text_retry_count
    render_meta["word_cap_fallback_truncate"] = fallback_truncate
    render_meta["executor_retry_count"] = total_retry_count
    render_meta["schema_retry_count"] = schema_retry_count
    render_meta["schema_salvage"] = bool(schema_salvage)
    render_meta["interrogative_retry_count"] = interrogative_retry_count
    render_meta["prev_phase"] = prev_phase
    render_meta["phase"] = phase_id
    render_meta["memory_short_turns"] = int((progress_state.get("memory_short_turns") or 0))
    render_meta["memory_short_source"] = memory_short_source
    render_meta["memory_short_turns_rendered"] = int(memory_short_turns_rendered)
    render_meta["memory_short_last_turn_idx"] = memory_short_last_turn_idx
    render_meta["memory_long_len"] = len(memory_long_compact or "")
    render_meta["memory_long_updated"] = bool((state.get("memory_meta") or {}).get("memory_long_updated", False))
    if question_forced_removed:
        render_meta["question_forced_removed"] = True
    render_meta["text_only_violations_count"] = text_only_violations_count
    render_meta["topic_selected"] = state.get("topic_selected", "")
    render_meta["topic_selected_source"] = state.get("topic_selected_source", "none")
    render_meta["phase_card_lookup_status"] = state.get("phase_card_lookup_status", "missing")
    render_meta["objective_delta"] = objective_delta
    render_meta["tactic"] = tactic
    render_meta["llm_raw_output_text"] = str(llm_raw_output_text or "")
    render_meta["llm_parsed_output"] = llm_parsed_output
    render_meta["normalized_output"] = normalize_executor_output(out)
    out["render_meta"] = render_meta

    return _enforce_executor_v2_contract(
        normalize_executor_output(out),
        style,
        constraints,
        question_allowed=question_allowed,
    )
