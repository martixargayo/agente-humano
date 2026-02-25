from __future__ import annotations

import json
import os
from copy import deepcopy

from langchain_core.messages import HumanMessage, SystemMessage

from ..elementos.render.executor_prompts import (
    EXECUTOR_OUTPUT_SCHEMA,
    EXECUTOR_SYSTEM_PROMPT,
    EXECUTOR_USER_PROMPT,
)
from ..phase_map import get_phase_map_v1

ExecutorOutput = dict
RenderConstraints = dict

_WORD_CAP_LIMIT = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP", "30") or 30)
_WORD_CAP_MAX_RERUNS = int(os.getenv("NEGOTIATION_EXECUTOR_WORD_CAP_MAX_RERUNS", "1") or 1)
_WORD_CAP_RETRY_INSTRUCTION = (
    f"REINTENTO_BREVEDAD: Devuelve JSON válido y limita response_text a máximo {_WORD_CAP_LIMIT} palabras."
)


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
    semantic_ledger = ((state.get("progress_state") or {}).get("semantic_ledger") if isinstance(state.get("progress_state"), dict) else {})
    assistant_last_message_ctx = str(state.get("assistant_last_message") or state.get("last_assistant_message") or "")

    prompt = EXECUTOR_USER_PROMPT.format(
        full_profiles_block=json.dumps({"persona": persona, "scene": scene, "style": style}, ensure_ascii=False),
        planner_semantic_output_json=json.dumps(planner_semantic_output, ensure_ascii=False),
        semantic_ledger_json=json.dumps(semantic_ledger if isinstance(semantic_ledger, dict) else {}, ensure_ascii=False),
        advisor_recs_json=json.dumps(state.get("advisor_recs", {}) if isinstance(state.get("advisor_recs"), dict) else {}, ensure_ascii=False),
        last_counterparty_utterance=extract_last_counterparty_utterance(state),
        memory_short=str(state.get("short_memory", "") or "").strip() or "SIN_MEMORIA_CORTA_AUN",
        memory_long=str(state.get("long_memory", "") or "").strip() or "SIN_RESUMEN_AUN",
        world_json=json.dumps(world_state, ensure_ascii=False),
        belief_json=json.dumps(state.get("belief_state", {}), ensure_ascii=False),
        retry_hint="",
        user_message=user_message,
        assistant_last_message=assistant_last_message_ctx,
        recent_history_text=str(state.get("recent_history_text", "") or ""),
        phase_map_json=json.dumps(state.get("phase_map_json") if isinstance(state.get("phase_map_json"), dict) else get_phase_map_v1(), ensure_ascii=False),
        speaker_of_user_message=str(state.get("speaker_of_user_message") or "seller").strip().lower(),
        output_schema=EXECUTOR_OUTPUT_SCHEMA.strip(),
    )

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
    fallback_truncate = False
    retry_prompt = _with_word_cap_instruction(prompt)

    while _word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT and reruns < _WORD_CAP_MAX_RERUNS:
        reruns += 1
        retry_messages = [
            SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
            HumanMessage(content=retry_prompt.strip()),
        ]
        retry_raw = deps.execute(retry_messages)
        retry_text = retry_raw if isinstance(retry_raw, str) else getattr(retry_raw, "content", "")
        out = normalize_executor_output(safe_json_load(retry_text))

    if _word_count(out.get("response_text", "")) > _WORD_CAP_LIMIT:
        fallback_truncate = True
        out = dict(out)
        out["response_text"] = _truncate_words(str(out.get("response_text", "")), _WORD_CAP_LIMIT)

    render_meta = dict(out.get("render_meta") or {}) if isinstance(out.get("render_meta"), dict) else {}
    render_meta["word_cap_limit"] = _WORD_CAP_LIMIT
    render_meta["word_cap_original_words"] = original_words
    render_meta["word_cap_reruns"] = reruns
    render_meta["word_cap_fallback_truncate"] = fallback_truncate
    out["render_meta"] = render_meta

    return _enforce_executor_v2_contract(normalize_executor_output(out), style, constraints)
