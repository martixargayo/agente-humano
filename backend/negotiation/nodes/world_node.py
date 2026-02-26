from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from ..llm_clients import get_planner_llm
from ..repo_prompts import WORLD_JUDGE_V4_SYSTEM_PROMPT, WORLD_JUDGE_V4_USER_PROMPT
from ..schemas import default_progress_state, default_semantic_ledger, default_world_state
from ..telemetry.llm_usage import extract_llm_usage


def _normalize_semantic_ledger(candidate: object, prev: dict | None = None) -> dict:
    base = default_semantic_ledger()
    source = candidate if isinstance(candidate, dict) else {}
    prev = prev if isinstance(prev, dict) else {}
    for key in base:
        chosen = source.get(key)
        if not isinstance(chosen, list):
            chosen = prev.get(key) if isinstance(prev.get(key), list) else []
        base[key] = [str(x).strip()[:180] for x in chosen if str(x).strip()][:6]
    return base


def _semantic_judge_fallback(*, ledger_prev: dict | None, degrade_reason: str = "judge_semantic_fallback") -> dict:
    return {
        "schema_version": "judge_semantic_v1",
        "topic_alignment": "on_topic",
        "reason_short": "Fallback semántico neutro.",
        "semantic_ledger": _normalize_semantic_ledger({}, ledger_prev),
        "ledger_update_notes": str(degrade_reason or "judge_semantic_fallback")[:160],
    }


def world_judge_llm(
    *,
    user_message: str,
    objective: str,
    world_state: dict,
    recent_history: str,
    turn_count: int,
    assistant_last_message: str = "",
    memory_short: str = "",
    memory_long: str = "",
    progress_state: dict | None = None,
    state: dict | None = None,
    **_: dict,
) -> tuple[dict, dict]:
    del objective, world_state, memory_short, memory_long, turn_count
    progress_state = progress_state or {}
    ledger_prev = _normalize_semantic_ledger((progress_state or {}).get("semantic_ledger", {}), {})

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    model_name = None
    rendered_prompt = ""
    text = ""
    try:
        model = get_planner_llm()
        model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
        user_prompt = WORLD_JUDGE_V4_USER_PROMPT.format(
            turn_idx=int((state or {}).get("turn_count", 0) or 0),
            speaker_of_user_message="seller",
            user_message=json.dumps(str(user_message or "")[:1000], ensure_ascii=False),
            assistant_last_message=json.dumps(str(assistant_last_message or "")[:1000], ensure_ascii=False),
            recent_history_text_compact=json.dumps(str(recent_history or "")[-1200:], ensure_ascii=False),
            semantic_ledger_prev_json=json.dumps(ledger_prev, ensure_ascii=False),
        )
        messages = [
            SystemMessage(content=WORLD_JUDGE_V4_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        rendered_prompt = "\n\n".join(
            f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
        )
        raw = model.invoke(messages)
        ended_wall = datetime.now(timezone.utc).isoformat()
        llm_usage = extract_llm_usage(raw)
        text = getattr(raw, "content", str(raw))
        candidate = json.loads(text)
        if not isinstance(candidate, dict):
            raise ValueError("judge_semantic_invalid_shape")
        if str(candidate.get("schema_version", "")) != "judge_semantic_v1":
            raise ValueError("judge_semantic_invalid_schema_version")
        topic_alignment = str(candidate.get("topic_alignment", "")).strip()
        if topic_alignment not in {"on_topic", "off_topic"}:
            raise ValueError("judge_semantic_invalid_topic_alignment")
        normalized = {
            "schema_version": "judge_semantic_v1",
            "topic_alignment": topic_alignment,
            "reason_short": str(candidate.get("reason_short", "") or "")[:220],
            "semantic_ledger": _normalize_semantic_ledger(candidate.get("semantic_ledger"), ledger_prev),
            "ledger_update_notes": str(candidate.get("ledger_update_notes", "") or "")[:240],
        }
        return normalized, {
            "judge_error_type": "",
            "judge_error_stage": "",
            "judge_retry_count": 0,
            "judge_llm_call_count": 1,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": False,
            "judge_start_ts": started_wall,
            "judge_end_ts": ended_wall,
            "judge_model": llm_usage.get("model") or model_name,
            "judge_tokens_in": llm_usage.get("tokens_in"),
            "judge_tokens_out": llm_usage.get("tokens_out"),
            "judge_input_prompt_rendered": rendered_prompt,
            "judge_output_text_rendered": str(text),
            "judge_output_payload_raw": candidate,
            "judge_prompt_variant": "v4_semantic",
        }
    except Exception as exc:
        ended_wall = datetime.now(timezone.utc).isoformat()
        fallback = _semantic_judge_fallback(ledger_prev=ledger_prev, degrade_reason=str(exc))
        error_stage = "llm_exception"
        if isinstance(exc, json.JSONDecodeError):
            error_stage = "parse_failed"
        elif isinstance(exc, ValueError):
            error_stage = "schema_invalid"
        return fallback, {
            "judge_error_type": exc.__class__.__name__,
            "judge_error_stage": error_stage,
            "judge_retry_count": 0,
            "judge_llm_call_count": 1,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": True,
            "judge_start_ts": started_wall,
            "judge_end_ts": ended_wall,
            "judge_prompt_variant": "v4_semantic",
            "judge_model": model_name,
            "judge_input_prompt_rendered": rendered_prompt,
            "judge_output_text_rendered": str(text),
        }


def world_updater_node(state: dict) -> dict:
    progress_state = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else default_progress_state()
    state["assistant_last_message"] = state.get("assistant_last_message") or state.get("last_assistant_message") or ""
    user_message = str(state.get("user_message", "") or "")
    recent_history = str(state.get("recent_history_text", "") or "")

    judgement, judge_meta = world_judge_llm(
        user_message=user_message,
        objective=str(state.get("objective", "") or ""),
        world_state=state.get("world_state") if isinstance(state.get("world_state"), dict) else default_world_state(),
        recent_history=recent_history,
        turn_count=int(state.get("turn_count", 0) or 0),
        assistant_last_message=str(state.get("assistant_last_message") or state.get("last_assistant_message") or ""),
        progress_state=progress_state,
        state=state,
    )

    state["semantic_judge"] = judgement
    state["world_debug"] = {
        "semantic_judge": judgement,
        "world_judge_meta": judge_meta,
    }
    return state


def flush_world_parallel_pending(state: dict) -> None:
    del state
    return
