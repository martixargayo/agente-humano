from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from .elementos.render.executor_prompts import (
    EXECUTOR_OUTPUT_SCHEMA,
    EXECUTOR_SYSTEM_PROMPT,
    EXECUTOR_USER_PROMPT,
)
from .elementos.render import resolve_render_profiles
from .elementos.render.render_contracts import RENDER_LIMITS
from .schemas import ExecutorOutput, RenderConstraints


_ALLOWED_TONES = {"friendly", "neutral", "tense"}


def safe_json_load(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}


def build_strategy_summary(state: dict, conversation_mode: str, policy_pack_active: str, policy_id: str) -> dict:
    policy_decision = state.get("policy_decision") or {}
    intent_hint = state.get("intent_hint") or {}
    precedence = state.get("precedence") or {}
    precedence_reason = ""
    if isinstance(precedence, dict):
        if "universal" in precedence:
            precedence_reason = (precedence.get("universal") or {}).get("reason", "")
        else:
            precedence_reason = precedence.get("reason", "")

    phase_effective = state.get("phase_effective")
    if not phase_effective:
        phase_effective = (state.get("progress_state") or {}).get("phase_state", {}).get("phase", "")

    return {
        "policy_id": policy_id,
        "micro_goal": policy_decision.get("micro_goal", ""),
        "risk_posture": policy_decision.get("risk_posture", ""),
        "why_short": policy_decision.get("why_short", ""),
        "inputs_used": policy_decision.get("inputs_used", []),
        "phase_effective": phase_effective,
        "intent_next_hint": intent_hint.get("next_action_hint", ""),
        "precedence_reason": precedence_reason,
        "conversation_mode": conversation_mode,
        "policy_pack_active": policy_pack_active,
    }


def _safe_neutral_fallback() -> str:
    return "Puedo ayudarte, pero necesito un poco más de contexto para responder bien."


def normalize_executor_output(raw: object) -> ExecutorOutput:
    base: ExecutorOutput = {
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

    response_text = str(raw.get("response_text", "")).strip()
    if not response_text:
        response_text = _safe_neutral_fallback()
    max_len = int(RENDER_LIMITS.get("response_text_max_len", 900))
    if len(response_text) > max_len:
        response_text = response_text[:max_len].rstrip()
    base["response_text"] = response_text

    asked_question = raw.get("asked_question")
    if isinstance(asked_question, bool):
        base["asked_question"] = asked_question
    else:
        base["asked_question"] = "?" in response_text

    requested = raw.get("requested_info_slots", [])
    if isinstance(requested, list):
        cleaned = [str(x).strip() for x in requested if str(x).strip()]
    else:
        cleaned = []
    max_slots = int(RENDER_LIMITS.get("requested_slots_max", 6))
    base["requested_info_slots"] = cleaned[:max_slots]

    tone_used = raw.get("tone_used", "neutral")
    if tone_used not in _ALLOWED_TONES:
        tone_used = "neutral"
    base["tone_used"] = tone_used

    followup_intent = raw.get("followup_intent")
    base["followup_intent"] = str(followup_intent) if followup_intent else None

    render_meta = raw.get("render_meta", {})
    base["render_meta"] = render_meta if isinstance(render_meta, dict) else {}

    return base


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
    persona, scene, style = resolve_render_profiles(
        {
            "persona_id": persona_profile.get("persona_id", "default"),
            "scene_id": scene_profile.get("scene_id", "default_chat"),
            "style_id": style_contract.get("style_id", "default"),
        }
    )
    persona.update(persona_profile)
    scene.update(scene_profile)
    style.update(style_contract)

    prompt = EXECUTOR_USER_PROMPT.format(
        conversation_mode=conversation_mode,
        policy_pack_active=policy_pack_active,
        policy_id=policy_id,
        micro_goal=strategy_summary.get("micro_goal", ""),
        risk_posture=strategy_summary.get("risk_posture", ""),
        why_short=strategy_summary.get("why_short", ""),
        inputs_used=strategy_summary.get("inputs_used", []),
        phase_effective=strategy_summary.get("phase_effective", ""),
        intent_next_hint=strategy_summary.get("intent_next_hint", ""),
        precedence_reason=strategy_summary.get("precedence_reason", ""),
        persona_json=json.dumps(persona, ensure_ascii=False),
        scene_json=json.dumps(scene, ensure_ascii=False),
        style_json=json.dumps(style, ensure_ascii=False),
        constraints_json=json.dumps(constraints_struct, ensure_ascii=False),
        memory_block=memory_block,
        world_json=json.dumps(world_state, ensure_ascii=False),
        user_message=user_message,
        output_schema=EXECUTOR_OUTPUT_SCHEMA.strip(),
    )

    messages = [
        SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
        HumanMessage(content=prompt.strip()),
    ]

    raw = deps.execute(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = safe_json_load(text)
    return normalize_executor_output(data)
