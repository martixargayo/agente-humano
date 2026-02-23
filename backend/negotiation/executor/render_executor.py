from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from ..elementos.render.executor_prompts import (
    EXECUTOR_OUTPUT_SCHEMA,
    EXECUTOR_SYSTEM_PROMPT,
    EXECUTOR_USER_PROMPT,
)
from ..llm_planning_context import build_executor_context_block_full
from ..elementos.render.render_contracts import RENDER_LIMITS
from ..schemas import ExecutorOutput, RenderConstraints


_ALLOWED_TONES = {"friendly", "neutral", "tense"}
_BELIEF_SUMMARY_MAX_CHARS = 1500
_BELIEF_SUMMARY_MAX_LIST = 6
_BELIEF_SUMMARY_MAX_DICT_KEYS = 8
_BELIEF_SUMMARY_MAX_STRING = 240


def _get_nested(value: object, path: List[str]) -> object:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _assign_nested(target: dict, path: List[str], value: object) -> None:
    current = target
    for key in path[:-1]:
        if key not in current or not isinstance(current.get(key), dict):
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


def _delete_nested(target: dict, path: List[str]) -> None:
    current = target
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            return
        current = current[key]
    if isinstance(current, dict):
        current.pop(path[-1], None)


def _should_include(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _trim_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= _BELIEF_SUMMARY_MAX_STRING:
            return value
        return value[: _BELIEF_SUMMARY_MAX_STRING].rstrip()
    if isinstance(value, list):
        return [_trim_value(item) for item in value[:_BELIEF_SUMMARY_MAX_LIST]]
    if isinstance(value, dict):
        trimmed = {}
        for key in sorted(value.keys())[:_BELIEF_SUMMARY_MAX_DICT_KEYS]:
            trimmed[key] = _trim_value(value[key])
        return trimmed
    return value


def _compact_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def summarize_belief_state_for_executor(belief_state: object) -> dict:
    if not isinstance(belief_state, dict):
        return {"summary": {}, "truncated": False, "keys": []}

    allowlist = [
        "planner_signals.interaction_health",
        "planner_signals.conflict_risk",
        "planner_signals.recommended_move",
        "planner_signals.recovery_mode",
        "planner_signals.clarity_vague",
        "belief_buckets.hypotheses",
        "belief_buckets.strategy_notes",
        "belief_buckets.risk_flags",
        "belief_buckets.watch_items",
    ]

    summary: dict = {}
    included: list[str] = []
    for entry in allowlist:
        path = entry.split(".")
        value = _get_nested(belief_state, path)
        if _should_include(value):
            _assign_nested(summary, path, _trim_value(value))
            included.append(entry)

    summary = _trim_value(summary)
    truncated = False
    payload = _compact_json(summary)
    if len(payload) > _BELIEF_SUMMARY_MAX_CHARS:
        truncated = True
        drop_order = [
            "belief_buckets.watch_items",
            "belief_buckets.strategy_notes",
            "belief_buckets.hypotheses",
            "belief_buckets.risk_flags",
            "planner_signals.recommended_move",
            "planner_signals.conflict_risk",
            "planner_signals.recovery_mode",
        ]
        for drop in drop_order:
            _delete_nested(summary, drop.split("."))
            payload = _compact_json(summary)
            if len(payload) <= _BELIEF_SUMMARY_MAX_CHARS:
                break

    if len(payload) > _BELIEF_SUMMARY_MAX_CHARS:
        truncated = True
        summary = {}
        health = _get_nested(belief_state, ["planner_signals", "interaction_health"])
        if _should_include(health):
            summary = {"planner_signals": {"interaction_health": _trim_value(health)}}
        payload = _compact_json(summary)

    final_keys = [key for key in included if _get_nested(summary, key.split(".")) is not None]
    return {"summary": summary, "truncated": truncated, "keys": sorted(final_keys)}


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


def build_strategy_summary(
    state: dict, conversation_mode: str, policy_pack_active: str, policy_id: str
) -> dict:
    policy_decision = state.get("policy_decision") or {}
    policy_hint = state.get("policy_hint") or {}
    intent_hint = state.get("intent_hint") or {}

    phase_effective = state.get("phase_effective")
    if not phase_effective:
        phase_effective = (state.get("progress_state") or {}).get("phase_state", {}).get("phase", "")

    next_hint = policy_hint.get("next_action_hint") or intent_hint.get("next_action_hint") or ""
    executor_instruction = state.get("executor_instruction") if isinstance(state.get("executor_instruction"), dict) else {}

    return {
        "policy_id": policy_id,
        "micro_goal": policy_decision.get("micro_goal", ""),
        "risk_posture": policy_decision.get("risk_posture", ""),
        "why_short": policy_decision.get("why_short", ""),
        "inputs_used": policy_decision.get("inputs_used", []),
        "phase_effective": phase_effective,
        "policy_next_hint": next_hint,
        "intent_next_hint": next_hint,
        "conversation_mode": conversation_mode,
        "policy_pack_active": policy_pack_active,
        "executor_instruction": executor_instruction,
    }


def _safe_neutral_fallback() -> str:
    return "Puedo ayudarte, pero necesito un poco más de contexto para responder bien."


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


def _enforce_executor_v2_contract(payload: ExecutorOutput, style_contract: dict, constraints_struct: dict) -> ExecutorOutput:
    out = dict(payload)
    text = str(out.get("response_text", "")).strip()
    max_words = int(style_contract.get("max_words", 30) or 30)
    if len(text.split()) > max_words:
        text = " ".join(text.split()[:max_words]).strip()
    max_questions = int(style_contract.get("max_questions", 1) or 1)
    if text.count("?") > max_questions:
        text = "?".join(text.split("?")[: max_questions + 1]).strip()
        if max_questions > 0 and not text.endswith("?"):
            text = text.rstrip(" .") + "?"
    if any(line.strip().startswith(("-", "*")) for line in text.splitlines()) or "**" in text or "#" in text:
        text = text.replace("*", "").replace("#", "").replace("\n", " ").strip()
    lowered = text.lower()
    leaks_detected = any(token in lowered for token in ["batna", "presupuesto máximo", "8000", "ocho mil"])
    leaks_detected = leaks_detected or bool(re.search(r"\b8[\.\s]?000\b", text, flags=re.IGNORECASE))
    leaks_detected = leaks_detected or bool(re.search(r"\b8k\b", text, flags=re.IGNORECASE))
    if leaks_detected:
        text = "Prefiero centrarnos en el estado real del coche y los papeles para avanzar con seguridad."
    out["response_text"] = text
    asked = "?" in text
    out["asked_question"] = asked
    slots = out.get("requested_info_slots", []) if isinstance(out.get("requested_info_slots"), list) else []
    cleaned_slots = [str(x).strip() for x in slots if str(x).strip()]
    if asked and not cleaned_slots:
        cleaned_slots = ["detalle_verificable"]
    if not asked:
        cleaned_slots = []
    out["requested_info_slots"] = cleaned_slots[:1]
    out["schema_version"] = "executor_v2"
    return normalize_executor_output(out)


def extract_last_counterparty_utterance(state: dict) -> str:
    direct = str(state.get("last_counterparty_utterance", "") or "").strip()
    if direct:
        return direct

    speaker = str(
        state.get("speaker_of_user_message")
        or state.get("speaker_of_last_message")
        or ((state.get("progress_state") or {}).get("speaker_of_user_message") if isinstance(state.get("progress_state"), dict) else "")
        or ""
    ).strip().lower()
    if speaker != "seller":
        return ""

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
    persona = deepcopy(persona_profile)
    scene = deepcopy(scene_profile)
    style = deepcopy(style_contract)
    constraints = deepcopy(constraints_struct)

    belief_summary = summarize_belief_state_for_executor(state.get("belief_state"))
    belief_summary_json = _compact_json(belief_summary.get("summary", {}))
    belief_summary_truncated = bool(belief_summary.get("truncated", False))
    belief_summary_keys = belief_summary.get("keys", [])

    if os.getenv("EXECUTOR_EPISTEMIC_CONTRACT_ENABLED", "0") == "1":
        constraints_epistemic = {
            "epistemic_style": constraints_struct.get("epistemic_style", "neutral"),
            "must_hedge": bool(constraints_struct.get("must_hedge", False)),
            "verify_first": bool(constraints_struct.get("verify_first", False)),
        }
    else:
        constraints_epistemic = {"epistemic_style": "neutral", "must_hedge": False, "verify_first": False}

    prompt = EXECUTOR_USER_PROMPT.format(
        full_profiles_block=build_executor_context_block_full(
            state.get("progress_state", {}),
            persona_profile=persona,
            scene_profile=scene,
            style_contract=style,
            constraints_struct=constraints,
        ),
        executor_instruction_json=json.dumps(strategy_summary.get("executor_instruction", {}), ensure_ascii=False),
        last_counterparty_utterance=extract_last_counterparty_utterance(state),
        memory_short=str(state.get("short_memory", "") or ""),
        memory_long=str(state.get("long_memory", "") or ""),
        world_json=json.dumps(world_state, ensure_ascii=False),
        belief_json=json.dumps(state.get("belief_state", {}), ensure_ascii=False),
        planner_output_summary=json.dumps(
            {
                "phase": strategy_summary.get("phase_effective", ""),
                "policy_id": policy_id,
                "plan_id": str((strategy_summary.get("executor_instruction") or {}).get("plan_id", "")),
            },
            ensure_ascii=False,
        ),
        user_message=user_message,
        speaker_of_user_message=str(
            state.get("speaker_of_user_message")
            or state.get("speaker_of_last_message")
            or ((state.get("progress_state") or {}).get("speaker_of_user_message") if isinstance(state.get("progress_state"), dict) else "")
            or "seller"
        ).strip().lower(),
        output_schema=EXECUTOR_OUTPUT_SCHEMA.strip(),
    )

    messages = [
        SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
        HumanMessage(content=prompt.strip()),
    ]

    raw = deps.execute(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = safe_json_load(text)
    return _enforce_executor_v2_contract(normalize_executor_output(data), style, constraints)
