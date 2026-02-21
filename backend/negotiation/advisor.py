from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from langchain_core.prompts import ChatPromptTemplate

from prompts import ADVISOR_SYSTEM_PROMPT, ADVISOR_USER_PROMPT
from .llm_clients import get_planner_llm

_advisor_prompt = ChatPromptTemplate.from_messages(
    [("system", ADVISOR_SYSTEM_PROMPT), ("user", ADVISOR_USER_PROMPT)]
)


def _compact_world_summary(world_state: dict) -> dict:
    buckets = (world_state or {}).get("world_buckets", {}) if isinstance(world_state, dict) else {}
    return {
        "offers": list((buckets.get("offers") or []))[:2],
        "constraints": list((buckets.get("constraints") or []))[:2],
        "interests": list((buckets.get("interests") or []))[:2],
        "requests": list((buckets.get("requests") or []))[:2],
    }


def _compact_belief_summary(belief_state: dict) -> dict:
    planner = (belief_state or {}).get("planner_signals", {}) if isinstance(belief_state, dict) else {}
    buckets = (belief_state or {}).get("belief_buckets", {}) if isinstance(belief_state, dict) else {}
    return {
        "planner_signals": planner,
        "hypotheses": list((buckets.get("hypotheses") or []))[:3],
        "risk_flags": list((buckets.get("risk_flags") or []))[:3],
    }


def _normalize_advisor(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {
            "diagnosis": [],
            "loop_or_waste_flags": [],
            "recommended_moves": [],
            "guardrails": [],
            "do_not_do": [],
            "suggested_utterances": [],
        }
    out = {
        "diagnosis": [str(x)[:160] for x in list(payload.get("diagnosis") or [])[:4]],
        "loop_or_waste_flags": [str(x)[:120] for x in list(payload.get("loop_or_waste_flags") or [])[:4]],
        "recommended_moves": [],
        "guardrails": [],
        "do_not_do": [str(x)[:140] for x in list(payload.get("do_not_do") or [])[:4]],
        "suggested_utterances": [str(x)[:180] for x in list(payload.get("suggested_utterances") or [])[:4]],
    }
    for item in list(payload.get("recommended_moves") or [])[:4]:
        if isinstance(item, dict):
            out["recommended_moves"].append(
                {
                    "title": str(item.get("title", ""))[:80],
                    "why": str(item.get("why", ""))[:140],
                    "how": str(item.get("how", ""))[:180],
                }
            )
    for item in list(payload.get("guardrails") or [])[:4]:
        if isinstance(item, dict):
            out["guardrails"].append(
                {
                    "if": str(item.get("if", ""))[:120],
                    "then": str(item.get("then", ""))[:160],
                }
            )
    return out


def build_advisor_recs(
    *,
    objective: str,
    recent_history: str,
    memory_short: str,
    memory_long: str,
    active_plan: dict | None,
    progress_state: dict,
    world_state: dict,
    belief_state: dict,
) -> tuple[dict, dict]:
    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    meta = {"advisor_ok": False, "advisor_latency_ms": 0, "advisor_error": "", "advisor_llm_called": False}
    payload = {
        "objective": str(objective or "")[:280],
        "recent_history": str(recent_history or "")[-1800:],
        "memory_short": str(memory_short or "")[-1200:],
        "memory_long": str(memory_long or "")[-1200:],
        "active_plan": active_plan if isinstance(active_plan, dict) else {},
        "progress_counters": {
            "no_progress_same_step_turns": int((progress_state or {}).get("no_progress_same_step_turns", 0) or 0),
            "judgement_missing_streak": int((progress_state or {}).get("judgement_missing_streak", 0) or 0),
            "loop_flags": list((progress_state or {}).get("loop_flags", []) or []),
        },
        "world_summary": _compact_world_summary(world_state),
        "belief_summary": _compact_belief_summary(belief_state),
    }
    try:
        messages = _advisor_prompt.format_messages(
            objective=payload["objective"],
            recent_history=json.dumps(payload["recent_history"], ensure_ascii=False),
            memory_short=json.dumps(payload["memory_short"], ensure_ascii=False),
            memory_long=json.dumps(payload["memory_long"], ensure_ascii=False),
            active_plan=json.dumps(payload["active_plan"], ensure_ascii=False),
            progress_counters=json.dumps(payload["progress_counters"], ensure_ascii=False),
            world_summary=json.dumps(payload["world_summary"], ensure_ascii=False),
            belief_summary=json.dumps(payload["belief_summary"], ensure_ascii=False),
        )
        raw = get_planner_llm().invoke(messages)
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_llm_called"] = True
        text = getattr(raw, "content", str(raw))
        recs = _normalize_advisor(json.loads(text))
        meta["advisor_ok"] = True
        return recs, {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
            "advisor_input_payload_raw": [
                {"role": getattr(msg, "type", "user"), "content": str(getattr(msg, "content", ""))}
                for msg in messages
            ],
            "advisor_input_prompt_rendered": "\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            ),
            "advisor_output_text_rendered": str(text),
            "advisor_output_payload_raw": recs,
        }
    except Exception as exc:
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_error"] = str(exc)[:180]
        return _normalize_advisor({}), {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
        }
