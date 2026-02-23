from __future__ import annotations

import json
import hashlib
import re
import time
import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from prompts import ADVISOR_SYSTEM_PROMPT, ADVISOR_USER_PROMPT
from .llm_clients import get_planner_llm


class AdvisorMove(BaseModel):
    title: str = ""
    why: str = ""
    how: str = ""


class AdvisorGuardrail(BaseModel):
    if_: str = Field(default="", alias="if")
    then: str = ""


class AdvisorStructuredPayload(BaseModel):
    diagnosis: list[str] = Field(default_factory=list)
    loop_or_waste_flags: list[str] = Field(default_factory=list)
    recommended_moves: list[AdvisorMove] = Field(default_factory=list)
    guardrails: list[AdvisorGuardrail] = Field(default_factory=list)
    do_not_do: list[str] = Field(default_factory=list)
    suggested_utterances: list[str] = Field(default_factory=list)


def _advisor_output_diagnostics(text: str, *, prefix: str = "advisor_output") -> dict:
    raw = str(text or "")
    mode = str(os.getenv("LIVETRACE2_MODE", "public") or "public").strip().lower()
    head = raw[:300]
    tail = raw[-300:] if len(raw) > 300 else raw
    if mode == "public":
        head = head[:120]
        tail = tail[:120]
    stripped = raw.lstrip("\ufeff\r\n\t ")
    first_char_codepoint = ord(stripped[0]) if stripped else None
    return {
        f"{prefix}_text_sha256": hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest(),
        f"{prefix}_text_snippet_head": head,
        f"{prefix}_text_snippet_tail": tail,
        f"{prefix}_text_len": len(raw),
        f"{prefix}_text_stripped_len": len(raw.strip()),
        f"{prefix}_first_char_codepoint": first_char_codepoint,
    }


def _extract_first_balanced_object(text: str) -> str | None:
    s = str(text or "")
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(s)):
        ch = s[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : idx + 1]
    return None


def _robust_json_parse(text: str) -> tuple[dict | None, str]:
    raw = str(text or "").lstrip("\ufeff")
    first_brace = raw.find("{")
    if first_brace > 0:
        raw = raw[first_brace:]
    candidates: list[tuple[str, str]] = [(raw, "raw")]
    extracted = _extract_first_balanced_object(raw)
    if extracted and extracted != raw:
        candidates.append((extracted, "balanced_object"))
    if extracted:
        no_trailing = re.sub(r",\s*([}\]])", r"\1", extracted)
        if no_trailing != extracted:
            candidates.append((no_trailing, "balanced_object_without_trailing_commas"))
        single_to_double = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', no_trailing)
        if single_to_double != no_trailing:
            candidates.append((single_to_double, "balanced_object_single_quotes_fixed"))

    for candidate, strategy in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, strategy
        except Exception:
            continue
    return None, "json_parse_failed"


def _retry_repair_json(*, broken_text: str, payload: dict) -> tuple[dict | None, str, str]:
    repair_messages = [
        SystemMessage(
            content=(
                "Devuelve SOLO JSON válido (sin markdown ni texto extra) con schema: "
                "{diagnosis:list[str], loop_or_waste_flags:list[str], recommended_moves:list[object], "
                "guardrails:list[object], do_not_do:list[str], suggested_utterances:list[str]}"
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "task": "repair_json",
                    "invalid_json": str(broken_text or "")[-3500:],
                    "context_payload": payload,
                },
                ensure_ascii=False,
            )
        ),
    ]
    repair_raw = get_planner_llm().invoke(repair_messages)
    repair_text = getattr(repair_raw, "content", str(repair_raw))
    parsed, strategy = _robust_json_parse(str(repair_text))
    if isinstance(parsed, dict):
        return parsed, f"repair_retry:{strategy}", str(repair_text)
    return None, "repair_failed", str(repair_text)


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
    meta = {
        "advisor_ok": False,
        "advisor_latency_ms": 0,
        "advisor_error": "",
        "advisor_error_type": "",
        "advisor_error_stage": "",
        "advisor_llm_called": False,
        "advisor_parse_strategy": "",
        "advisor_repair_parse_strategy": "",
    }
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

    messages = [
        SystemMessage(content=ADVISOR_SYSTEM_PROMPT),
        HumanMessage(
            content=ADVISOR_USER_PROMPT.format(
                objective=payload["objective"],
                recent_history=json.dumps(payload["recent_history"], ensure_ascii=False),
                memory_short=json.dumps(payload["memory_short"], ensure_ascii=False),
                memory_long=json.dumps(payload["memory_long"], ensure_ascii=False),
                active_plan=json.dumps(payload["active_plan"], ensure_ascii=False),
                progress_counters=json.dumps(payload["progress_counters"], ensure_ascii=False),
                world_summary=json.dumps(payload["world_summary"], ensure_ascii=False),
                belief_summary=json.dumps(payload["belief_summary"], ensure_ascii=False),
            )
        ),
    ]

    input_payload_raw = {
        "objective_len": len(str(payload.get("objective", ""))),
        "recent_history_len": len(str(payload.get("recent_history", ""))),
        "memory_short_len": len(str(payload.get("memory_short", ""))),
        "memory_long_len": len(str(payload.get("memory_long", ""))),
        "active_plan_keys": sorted(list((payload.get("active_plan") or {}).keys()))[:16],
        "progress_counters_keys": sorted(list((payload.get("progress_counters") or {}).keys()))[:16],
        "world_summary_keys": sorted(list((payload.get("world_summary") or {}).keys()))[:16],
        "belief_summary_keys": sorted(list((payload.get("belief_summary") or {}).keys()))[:16],
    }

    try:
        text = ""
        repair_text = ""
        initial_diag: dict = {}
        repair_diag: dict = {}
        parse_strategy = ""
        repair_parse_strategy = ""
        parsed: dict | None = None

        meta["advisor_error_stage"] = "structured_output"
        llm = get_planner_llm()
        try:
            structured = llm.with_structured_output(AdvisorStructuredPayload)
            structured_result = structured.invoke(messages)
            meta["advisor_llm_called"] = True
            if isinstance(structured_result, AdvisorStructuredPayload):
                parsed = structured_result.model_dump(by_alias=True)
            elif hasattr(structured_result, "model_dump"):
                parsed = structured_result.model_dump(by_alias=True)
            elif isinstance(structured_result, dict):
                parsed = structured_result
            parse_strategy = "structured_output"
        except Exception:
            meta["advisor_error_stage"] = "llm_invoke"
            raw = llm.invoke(messages)
            meta["advisor_llm_called"] = True
            text = getattr(raw, "content", str(raw))
            initial_diag = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")
            meta["advisor_error_stage"] = "json_parse"
            parsed, parse_strategy = _robust_json_parse(str(text))
            if not isinstance(parsed, dict):
                meta["advisor_error_stage"] = "repair_retry"
                repaired, repair_strategy, repair_text = _retry_repair_json(broken_text=str(text), payload=payload)
                repair_parse_strategy = repair_strategy
                repair_diag = _advisor_output_diagnostics(str(repair_text), prefix="advisor_repair_output")
                if isinstance(repaired, dict):
                    parsed = repaired
                    parse_strategy = repair_strategy
                else:
                    raise json.JSONDecodeError("advisor_invalid_json_after_repair", str(repair_text), 0)
        recs = _normalize_advisor(parsed)
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_ok"] = True
        meta["advisor_error_stage"] = ""
        meta["advisor_parse_strategy"] = parse_strategy
        meta["advisor_repair_parse_strategy"] = repair_parse_strategy
        return recs, {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
            "advisor_input_payload_raw": input_payload_raw,
            "advisor_input_prompt_rendered": "\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            ),
            "advisor_output_text_rendered": str(text),
            "advisor_output_payload_raw": recs,
            "advisor_parse_strategy": parse_strategy,
            "advisor_repair_parse_strategy": repair_parse_strategy,
            **initial_diag,
            **repair_diag,
        }
    except Exception as exc:
        text = locals().get("text", "")
        repair_text = locals().get("repair_text", "")
        diagnostics = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")
        repair_diagnostics = _advisor_output_diagnostics(str(repair_text), prefix="advisor_repair_output")
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_error"] = f"{exc.__class__.__name__}: {str(exc)}"[:220]
        meta["advisor_error_type"] = exc.__class__.__name__
        if not meta.get("advisor_error_stage"):
            meta["advisor_error_stage"] = "unknown"
        return _normalize_advisor({}), {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
            "advisor_input_payload_raw": input_payload_raw,
            "advisor_output_payload_raw": {
                "error_type": meta.get("advisor_error_type", "unknown"),
                "error_message": meta.get("advisor_error", "unknown_error"),
                "stage": meta.get("advisor_error_stage", "unknown"),
                "advisor_parse_strategy": meta.get("advisor_parse_strategy") or locals().get("parse_strategy", ""),
                "advisor_repair_parse_strategy": meta.get("advisor_repair_parse_strategy") or locals().get("repair_parse_strategy", ""),
                **diagnostics,
                **repair_diagnostics,
            },
            **diagnostics,
            **repair_diagnostics,
        }
