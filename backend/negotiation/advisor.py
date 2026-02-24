from __future__ import annotations

import json
import hashlib
import time
import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from .repo_prompts import (
    ADVISOR_SYSTEM_PROMPT,
    ADVISOR_USER_PROMPT,
    ADVISOR_V2_SYSTEM_PROMPT,
    ADVISOR_V2_USER_PROMPT,
)
from .executor.render_executor import extract_last_counterparty_utterance
from .llm_clients import get_advisor_llm
from .llm_background import canonical_speaker_for_turn
from .llm_planning_context import (
    build_advisor_context_block_full,
    build_belief_digest,
    build_full_roleplay_profiles,
    build_objective_summary,
    build_world_digest,
    build_world_full_compact,
    compact_json_for_prompt,
)


def _find_unescaped_newline_in_string(text: str) -> bool:
    in_string = False
    escape = False
    for ch in str(text or ""):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            elif ch == "\n":
                return True
            continue
        if ch == '"':
            in_string = True
    return False


def _escape_newlines_inside_strings(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in str(text or ""):
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_string = True
        out.append(ch)
    return "".join(out)


def _json_error_details(text: str) -> dict:
    raw = str(text or "")
    try:
        json.loads(raw)
        return {}
    except json.JSONDecodeError as exc:
        pos = int(exc.pos or 0)
        start = max(0, pos - 80)
        end = min(len(raw), pos + 80)
        return {
            "json_error_msg": str(exc.msg),
            "json_error_pos": pos,
            "json_error_lineno": int(exc.lineno or 0),
            "json_error_colno": int(exc.colno or 0),
            "json_error_context": raw[start:end],
        }
    except Exception as exc:
        return {"json_error_msg": f"non_json_decode_error:{exc.__class__.__name__}"}


def _extract_first_balanced_json_object(text: str) -> str:
    raw = str(text or "")
    start = raw.find("{")
    if start < 0:
        return ""
    in_string = False
    escape = False
    depth = 0
    for idx in range(start, len(raw)):
        ch = raw[idx]
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
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : idx + 1]
    return raw[start:]


def _close_json_structures_locally(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw
    fixed = raw
    missing_brackets = max(0, fixed.count("[") - fixed.count("]"))
    if missing_brackets:
        fixed = f"{fixed}{']' * missing_brackets}"
    missing_braces = max(0, fixed.count("{") - fixed.count("}"))
    if missing_braces:
        fixed = f"{fixed}{'}' * missing_braces}"
    return fixed


def _advisor_output_diagnostics(text: str, *, prefix: str = "advisor_output") -> dict:
    raw = str(text or "")
    mode = str(os.getenv("LIVETRACE2_MODE", "public") or "public").strip().lower()
    head = raw[:300]
    tail = raw[-300:] if len(raw) > 300 else raw
    mid_start = max(0, (len(raw) // 2) - 200)
    mid_end = min(len(raw), mid_start + 400)
    middle = raw[mid_start:mid_end]
    if mode == "public":
        head = head[:120]
        tail = tail[:120]
        middle = middle[:120]
    stripped = raw.lstrip("\ufeff\r\n\t ")
    first_char_codepoint = ord(stripped[0]) if stripped else None
    details = {
        f"{prefix}_text_sha256": hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest(),
        f"{prefix}_text_snippet_head": head,
        f"{prefix}_text_snippet_middle": middle,
        f"{prefix}_text_snippet_tail": tail,
        f"{prefix}_text_len": len(raw),
        f"{prefix}_text_stripped_len": len(raw.strip()),
        f"{prefix}_first_char_codepoint": first_char_codepoint,
        f"{prefix}_brace_open_count": raw.count("{"),
        f"{prefix}_brace_close_count": raw.count("}"),
        f"{prefix}_bracket_open_count": raw.count("["),
        f"{prefix}_bracket_close_count": raw.count("]"),
        f"{prefix}_has_unescaped_newline_in_string": _find_unescaped_newline_in_string(raw),
    }
    if mode == "internal":
        details[f"{prefix}_text_full"] = raw
    return details


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
        "suggested_utterances": [str(x)[:180] for x in list(payload.get("suggested_utterances") or [])[:1]],
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
    user_message: str = "",
    state: dict | None = None,
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
        "advisor_reason_code": "",
        "advisor_prompt_variant": "",
        "use_advisor_v2": False,
        "advisor_llm_call_count": 0,
    }
    use_v2 = True
    meta["advisor_prompt_variant"] = "v2" if use_v2 else "v1"
    meta["use_advisor_v2"] = bool(use_v2)
    persona_profile, scene_profile, style_contract, constraints_struct = build_full_roleplay_profiles(progress_state)
    objective_summary = build_objective_summary(objective, scene_profile, persona_profile)
    speaker_of_last_message = canonical_speaker_for_turn(
        progress_state=progress_state,
        state=state,
        default="seller",
    )
    world_diff = (progress_state or {}).get("world_diff") if isinstance((progress_state or {}).get("world_diff"), dict) else {}
    payload = {
        "objective": str(objective or "")[:280],
        "objective_summary": objective_summary,
        "recent_history": str(recent_history or "")[-1800:],
        "user_message": str(user_message or "")[:1000],
        "memory_short": str(memory_short or "")[-1200:],
        "memory_long": str(memory_long or "")[-1200:],
        "active_plan": active_plan if isinstance(active_plan, dict) else {},
        "phase_state": (progress_state or {}).get("phase_state") if isinstance((progress_state or {}).get("phase_state"), dict) else {},
        "policy_state": (progress_state or {}).get("policy_state") if isinstance((progress_state or {}).get("policy_state"), dict) else {},
        "progress_counters": {
            "no_progress_same_step_turns": int((progress_state or {}).get("no_progress_same_step_turns", 0) or 0),
            "judgement_missing_streak": int((progress_state or {}).get("judgement_missing_streak", 0) or 0),
            "loop_flags": list((progress_state or {}).get("loop_flags", []) or []),
        },
        "world_summary": _compact_world_summary(world_state),
        "belief_summary": _compact_belief_summary(belief_state),
        "full_profiles_block": build_advisor_context_block_full(progress_state),
        "speaker_of_last_message": speaker_of_last_message,
        "last_counterparty_utterance": extract_last_counterparty_utterance(
            {
                "recent_history": recent_history,
                "recent_history_text": recent_history,
                "user_message": user_message,
                "speaker_of_user_message": speaker_of_last_message,
            }
        ),
        "world_digest_json": json.dumps(build_world_digest(world_state or {}, world_diff), ensure_ascii=False),
        "world_full_json": compact_json_for_prompt(build_world_full_compact(world_state or {}), max_chars=8000),
        "belief_digest_json": json.dumps(build_belief_digest(belief_state or {}), ensure_ascii=False),
        "progress_counters_json": json.dumps(
            {
                "no_progress_same_step_turns": int((progress_state or {}).get("no_progress_same_step_turns", 0) or 0),
                "judgement_missing_streak": int((progress_state or {}).get("judgement_missing_streak", 0) or 0),
                "loop_flags": list((progress_state or {}).get("loop_flags", []) or []),
            },
            ensure_ascii=False,
        ),
    }

    if use_v2:
        system_prompt = ADVISOR_V2_SYSTEM_PROMPT
        user_prompt = ADVISOR_V2_USER_PROMPT.format(
            full_profiles_block=payload["full_profiles_block"],
            objective_summary=payload["objective_summary"],
            speaker_of_last_message=payload["speaker_of_last_message"],
            last_counterparty_utterance=json.dumps(payload["last_counterparty_utterance"], ensure_ascii=False),
            user_message=json.dumps(payload["user_message"], ensure_ascii=False),
            recent_history_text=json.dumps(payload["recent_history"], ensure_ascii=False),
            memory_short=json.dumps(payload["memory_short"], ensure_ascii=False),
            memory_long=json.dumps(payload["memory_long"], ensure_ascii=False),
            active_plan_json=json.dumps(payload["active_plan"], ensure_ascii=False),
            phase_state_json=json.dumps(payload["phase_state"], ensure_ascii=False),
            policy_state_json=json.dumps(payload["policy_state"], ensure_ascii=False),
            world_digest_json=payload["world_digest_json"],
            world_full_json=payload["world_full_json"],
            belief_digest_json=payload["belief_digest_json"],
            progress_counters_json=payload["progress_counters_json"],
        )
    else:
        system_prompt = ADVISOR_SYSTEM_PROMPT
        user_prompt = ADVISOR_USER_PROMPT.format(
            objective=payload["objective"],
            recent_history=json.dumps(payload["recent_history"], ensure_ascii=False),
            memory_short=json.dumps(payload["memory_short"], ensure_ascii=False),
            memory_long=json.dumps(payload["memory_long"], ensure_ascii=False),
            active_plan=json.dumps(payload["active_plan"], ensure_ascii=False),
            progress_counters=json.dumps(payload["progress_counters"], ensure_ascii=False),
            world_summary=json.dumps(payload["world_summary"], ensure_ascii=False),
            belief_summary=json.dumps(payload["belief_summary"], ensure_ascii=False),
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
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
        parse_error: dict = {}
        parse_strategy = ""
        llm = get_advisor_llm()
        meta["advisor_model"] = getattr(llm, "model_name", None) or getattr(llm, "model", None)
        response_format_mode = ""
        llm_for_invoke = llm
        if os.getenv("NEGOTIATION_ADVISOR_RESPONSE_FORMAT", "json_object").strip().lower() == "json_object":
            try:
                llm_for_invoke = llm.bind(response_format={"type": "json_object"})
                response_format_mode = "json_object"
            except Exception:
                llm_for_invoke = llm
                response_format_mode = "unsupported"

        raw = llm_for_invoke.invoke(messages)
        meta["advisor_llm_called"] = True
        meta["advisor_llm_call_count"] = 1
        meta["advisor_response_format_mode"] = response_format_mode
        text = getattr(raw, "content", str(raw))
        initial_diag = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")

        parsed: dict | None = None
        try:
            loaded = json.loads(str(text))
            parse_strategy = "json_loads"
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                meta["advisor_error_stage"] = "schema_invalid"
                meta["advisor_reason_code"] = "advisor_output_not_object"
        except Exception:
            raw_text = str(text)
            repaired = _escape_newlines_inside_strings(raw_text)
            extracted = _extract_first_balanced_json_object(repaired)
            closed = _close_json_structures_locally(extracted or repaired)
            parse_strategy = ""
            for candidate, strategy_name in [
                (repaired, "json_loads_escaped_newlines"),
                (extracted, "json_loads_balanced_object"),
                (closed, "json_loads_balanced_closed"),
            ]:
                if not str(candidate).strip():
                    continue
                try:
                    loaded = json.loads(str(candidate))
                except Exception:
                    continue
                if isinstance(loaded, dict):
                    parsed = loaded
                    parse_strategy = strategy_name
                    meta["advisor_local_repair_applied"] = strategy_name
                    break
            if not isinstance(parsed, dict):
                parse_error = _json_error_details(raw_text)
                meta["advisor_error_stage"] = "parse_failed"
                meta["advisor_reason_code"] = "advisor_invalid_json"

        if isinstance(parsed, dict):
            recs = _normalize_advisor(parsed)
            if recs == _normalize_advisor({}) and parsed != {}:
                meta["advisor_error_stage"] = "schema_invalid"
                meta["advisor_reason_code"] = "advisor_schema_invalid"
            else:
                meta["advisor_error_stage"] = ""
                meta["advisor_reason_code"] = ""
        else:
            recs = _normalize_advisor({})

        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_ok"] = meta.get("advisor_error_stage", "") == ""
        meta["advisor_parse_strategy"] = parse_strategy
        return recs, {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
            "advisor_input_payload_raw": input_payload_raw,
            "advisor_input_prompt_rendered": "\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            ),
            "advisor_payload_chars": len("\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            )),
            "advisor_output_text_rendered": str(text),
            "advisor_output_payload_raw": recs,
            "advisor_parse_strategy": parse_strategy,
            "advisor_parse_error": parse_error,
            **initial_diag,
        }
    except Exception as exc:
        text = locals().get("text", "")
        parse_error = locals().get("parse_error", {})
        diagnostics = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")
        ended_wall = datetime.now(timezone.utc).isoformat()
        meta["advisor_error"] = f"{exc.__class__.__name__}: {str(exc)}"[:220]
        meta["advisor_error_type"] = exc.__class__.__name__
        meta["advisor_error_stage"] = "llm_exception"
        if meta.get("advisor_llm_call_count", 0) == 0:
            meta["advisor_llm_call_count"] = 1
        return _normalize_advisor({}), {
            **meta,
            "advisor_latency_ms": int((time.perf_counter() - started) * 1000),
            "advisor_start_ts": started_wall,
            "advisor_end_ts": ended_wall,
            "advisor_input_payload_raw": input_payload_raw,
            "advisor_input_prompt_rendered": "\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            ),
            "advisor_output_text_rendered": str(text),
            "advisor_payload_chars": len("\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            )),
            "advisor_output_payload_raw": {
                "error_type": meta.get("advisor_error_type", "unknown"),
                "error_message": meta.get("advisor_error", "unknown_error"),
                "stage": meta.get("advisor_error_stage", "unknown"),
                "advisor_parse_strategy": meta.get("advisor_parse_strategy") or locals().get("parse_strategy", ""),
                "advisor_parse_error": parse_error,
                **diagnostics,
            },
            **diagnostics,
        }
