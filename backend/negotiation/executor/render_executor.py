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

ExecutorOutput = dict
RenderConstraints = dict

_WORD_CAP_LIMIT = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP", "40") or 40)
_WORD_CAP_MAX_RERUNS = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP_MAX_RERUNS", "1") or 1)
_WORD_CAP_RETRY_INSTRUCTION = f"REINTENTO_BREVEDAD: Devuelve JSON válido y limita response_text a máximo {_WORD_CAP_LIMIT} palabras."
_SCHEMA_RETRY_INSTRUCTION = "REINTENTO_ESQUEMA: Devuelve SOLO JSON executor_v2 con schema_version y response_text. Sin otras claves."
_PROMPT_SWAP_V2_ENABLED = str(os.getenv("NEGOTIATION_PROMPT_SWAP_V2_ENABLED", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
_TEXT_ONLY_FORBIDDEN_RE = re.compile(r"\b(muéstrame|muestrame|enséñame|ensename|envíame|enviame|adjunta|pásame|pasame|tráeme|traeme)\b", re.IGNORECASE)
_INTERROGATIVE_START_RE = re.compile(
    r'(?i)(^|[.!]\s+)\s*(cómo|como|qué|que|cuándo|cuando|dónde|donde|por qué|porque|cuánto|cuanto|cuál|cual|quién|quien)\b'
)
_INTERROGATIVE_PHRASE_RE = re.compile(
    r'(?i)\b(me gustaría saber|quisiera saber|podrías decirme|me puedes decir|necesito saber|dime si)\b'
)
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
    need_info_slots: list[str] | None = None,
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

    asked_question = bool(data.get("asked_question", False)) or _looks_like_question_es(data["response_text"])

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
        if need_info_slots:
            requested_slots = [str(x).strip()[:32] for x in need_info_slots if str(x).strip()][:3]
        elif not requested_slots:
            requested_slots = _infer_requested_slots(data["response_text"])
        data["requested_info_slots"] = requested_slots[:3]
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


def _extract_need_info_slots(text: str) -> list[str]:
    m = re.search(r"(?im)^\s*NECESITA_INFO\s*:\s*(.+)$", str(text or ""))
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    slots = []
    for part in raw.split(","):
        slot = re.sub(r"\s+", "_", part.strip().lower()).strip("_")
        if slot in _ALLOWED_NEED_INFO_SLOTS and slot not in slots:
            slots.append(slot)
    return slots[:2]


def _user_asked_direct_question(msg: str) -> bool:
    return _looks_like_question_es(msg)


def _looks_like_question_es(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    if "?" in t or "¿" in t:
        return True
    if _INTERROGATIVE_START_RE.search(t):
        return True
    if _INTERROGATIVE_PHRASE_RE.search(t):
        return True
    return False


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




def _infer_requested_slots(response_text: str) -> list[str]:
    lowered = str(response_text or "").lower()
    slots: list[str] = []
    mapping = [
        ("saludo", ["qué tal", "como estas", "cómo estás", "hola"]),
        ("precio_objetivo", ["precio", "cuánto", "cuanto"]),
        ("motivo_venta", ["motivo", "por qué", "porque lo vendes"]),
        ("estado_general", ["estado", "general"]),
        ("mantenimiento", ["mantenimiento", "revisión", "revision"]),
        ("documentacion", ["documentación", "documentacion", "papeles", "trámites", "tramites"]),
        ("pago_fecha", ["pago", "fecha", "entrega"]),
        ("contexto", ["detalles", "contexto"])
    ]
    for slot, keys in mapping:
        if any(k in lowered for k in keys):
            slots.append(slot)
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
    need_info_slots = []
    if isinstance(state.get("planner_need_info_slots"), list):
        need_info_slots = [str(x).strip() for x in state.get("planner_need_info_slots") if str(x).strip()]
    else:
        hint_text = str(planner_semantic_output.get("next_move_hint") or "") if isinstance(planner_semantic_output, dict) else ""
        need_info_slots = _extract_need_info_slots(hint_text)

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
        need_info_slots_json=json.dumps(need_info_slots, ensure_ascii=False),
        phase=phase_card.get("phase", phase_id),
        phase_do_text=phase_card.get("do_text", ""),
        phase_tecnicas_text=phase_card.get("tecnicas_text", ""),
        phase_evitar_text=phase_card.get("evitar_text", ""),
        phase_question_policy=phase_card.get("question_policy", ""),
        phase_topics_json=json.dumps(phase_card.get("topics", []), ensure_ascii=False),
        topic_selected=topic_selected,
        lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
        lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
        lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
        recent_history_compact=str(state.get("short_memory") or state.get("recent_history_text", "") or "").strip() or "SIN_MEMORIA_CORTA_AUN",
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
    data = safe_json_load(raw if isinstance(raw, str) else getattr(raw, "content", ""))
    data, schema_salvage = _salvage_response_text(data)

    schema_retry_count = 0
    if not _is_valid_executor_v2_payload(data):
        schema_retry_count = 1
        schema_retry_prompt = _with_retry_instruction(prompt, _SCHEMA_RETRY_INSTRUCTION)
        retry_messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=schema_retry_prompt.strip()),
        ]
        retry_raw = deps.execute(retry_messages)
        retry_data = safe_json_load(retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", ""))
        retry_data, schema_salvage_retry = _salvage_response_text(retry_data)
        schema_salvage = schema_salvage or schema_salvage_retry
        data = retry_data

    out = normalize_executor_output(data)
    original_words = _word_count(str(out.get("response_text", "")))

    question_allowed = bool(need_info_slots)
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
        retry_data_q = safe_json_load(retry_raw_q if isinstance(retry_raw_q, str) else getattr(retry_raw_q, "content", ""))
        retry_data_q, schema_salvage_retry = _salvage_response_text(retry_data_q)
        schema_salvage = schema_salvage or schema_salvage_retry
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
        retry_data = safe_json_load(retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", ""))
        retry_data, schema_salvage_retry = _salvage_response_text(retry_data)
        schema_salvage = schema_salvage or schema_salvage_retry
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
    render_meta["memory_short_turns"] = int((((state.get("progress_state") or {}).get("memory_short_turns")) or 0))
    render_meta["memory_long_updated"] = bool((state.get("memory_meta") or {}).get("memory_long_updated", False))
    if question_forced_removed:
        render_meta["question_forced_removed"] = True
    render_meta["text_only_violations_count"] = text_only_violations_count
    render_meta["topic_selected"] = state.get("topic_selected", "")
    render_meta["topic_selected_source"] = state.get("topic_selected_source", "none")
    render_meta["phase_card_lookup_status"] = state.get("phase_card_lookup_status", "missing")
    out["render_meta"] = render_meta

    return _enforce_executor_v2_contract(
        normalize_executor_output(out),
        style,
        constraints,
        need_info_slots=need_info_slots,
        question_allowed=question_allowed,
    )
