from __future__ import annotations

import json
import hashlib
import re
import time
import os
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from prompts import (
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

    if _find_unescaped_newline_in_string(raw):
        candidates.append((_escape_newlines_inside_strings(raw), "raw_newlines_escaped"))

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

    seen: set[str] = set()
    for candidate, strategy in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, strategy
        except Exception:
            continue
    return None, "json_parse_failed"


def _invoke_json_mode(messages: list, llm) -> tuple[str, str]:
    json_system = SystemMessage(
        content=(
            "Return ONLY valid JSON object. No markdown, no prose, no prefix. "
            "All string values must be single-line (no raw newlines). "
            "Keep concise: diagnosis<=4, loop_or_waste_flags<=4, recommended_moves<=3, "
            "guardrails<=3, do_not_do<=4, suggested_utterances<=3."
        )
    )
    raw = llm.bind(response_format={"type": "json_object"}).invoke([json_system, *messages])
    return getattr(raw, "content", str(raw)), "json_mode"


def _retry_repair_json(
    *,
    broken_text: str,
    payload: dict,
    parse_error: dict,
    initial_diagnostics: dict,
    llm,
) -> tuple[dict | None, str, str, dict]:
    repair_messages = [
        SystemMessage(
            content=(
                "Devuelve SOLO JSON válido (sin markdown ni texto extra). "
                "No repitas el texto original si está roto. "
                "Si el error indica truncación o desbalanceo, reemite el objeto completo y corto."
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "task": "repair_json",
                    "invalid_json": str(broken_text or "")[-3500:],
                    "json_error": parse_error,
                    "invalid_json_diagnostics": initial_diagnostics,
                    "schema": {
                        "diagnosis": ["str"],
                        "loop_or_waste_flags": ["str"],
                        "recommended_moves": [{"title": "str", "why": "str", "how": "str"}],
                        "guardrails": [{"if": "str", "then": "str"}],
                        "do_not_do": ["str"],
                        "suggested_utterances": ["str"],
                    },
                    "context_payload": payload,
                },
                ensure_ascii=False,
            )
        ),
    ]
    repair_input_prompt_rendered = "\n\n".join(
        f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in repair_messages
    )
    repair_raw = llm.invoke(repair_messages)
    repair_text = getattr(repair_raw, "content", str(repair_raw))
    parsed, strategy = _robust_json_parse(str(repair_text))
    extra = {
        "repair_invoke_called": True,
        "advisor_repair_input_prompt_rendered": repair_input_prompt_rendered,
    }
    if isinstance(parsed, dict):
        return parsed, f"repair_retry:{strategy}", str(repair_text), extra

    if hashlib.sha256(str(repair_text).encode("utf-8", errors="ignore")).hexdigest() == hashlib.sha256(
        str(broken_text).encode("utf-8", errors="ignore")
    ).hexdigest():
        extra["advisor_reason_code"] = "repair_same_as_initial"

    try:
        forced_text, mode = _invoke_json_mode(repair_messages, llm)
        forced_messages = [
            SystemMessage(
                content=(
                    "Return ONLY valid JSON object. No markdown, no prose, no prefix. "
                    "All string values must be single-line (no raw newlines). "
                    "Keep concise: diagnosis<=4, loop_or_waste_flags<=4, recommended_moves<=3, "
                    "guardrails<=3, do_not_do<=4, suggested_utterances<=3."
                )
            ),
            *repair_messages,
        ]
        extra["advisor_repair_json_mode_input_prompt_rendered"] = "\n\n".join(
            f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in forced_messages
        )
        forced_parsed, forced_strategy = _robust_json_parse(forced_text)
        if isinstance(forced_parsed, dict):
            return forced_parsed, f"repair_retry:{mode}:{forced_strategy}", forced_text, extra
    except Exception as exc:
        extra["advisor_repair_json_mode_error"] = f"{exc.__class__.__name__}:{str(exc)[:80]}"

    return None, "repair_failed", str(repair_text), extra


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
        "advisor_repair_parse_strategy": "",
        "repair_invoke_called": False,
        "advisor_reason_code": "",
        "advisor_prompt_variant": "",
        "use_advisor_v2": False,
    }
    use_v2 = os.getenv("USE_ADVISOR_V2", "0") == "1"
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
        repair_text = ""
        initial_diag: dict = {}
        repair_diag: dict = {}
        parse_error: dict = {}
        parse_strategy = ""
        repair_parse_strategy = ""
        parsed: dict | None = None

        llm = get_advisor_llm()
        meta["advisor_model"] = getattr(llm, "model_name", None) or getattr(llm, "model", None)

        meta["advisor_error_stage"] = "structured_output"
        structured_error = ""
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
        except Exception as exc:
            structured_error = f"{exc.__class__.__name__}: {str(exc)[:160]}"

        if not isinstance(parsed, dict):
            meta["advisor_error_stage"] = "json_mode"
            try:
                text, parse_strategy = _invoke_json_mode(messages, llm)
                meta["advisor_llm_called"] = True
                initial_diag = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")
                parse_error = _json_error_details(str(text))
                parsed, robust_strategy = _robust_json_parse(str(text))
                parse_strategy = f"{parse_strategy}:{robust_strategy}"
            except Exception:
                meta["advisor_error_stage"] = "llm_invoke"
                raw = llm.invoke(messages)
                meta["advisor_llm_called"] = True
                text = getattr(raw, "content", str(raw))
                initial_diag = _advisor_output_diagnostics(str(text), prefix="advisor_initial_output")
                parse_error = _json_error_details(str(text))
                meta["advisor_error_stage"] = "json_parse"
                parsed, parse_strategy = _robust_json_parse(str(text))

        if not isinstance(parsed, dict):
            meta["advisor_error_stage"] = "repair_retry"
            repaired, repair_strategy, repair_text, repair_extra = _retry_repair_json(
                broken_text=str(text),
                payload=payload,
                parse_error=parse_error,
                initial_diagnostics=initial_diag,
                llm=llm,
            )
            repair_parse_strategy = repair_strategy
            repair_diag = _advisor_output_diagnostics(str(repair_text), prefix="advisor_repair_output")
            if repair_extra.get("repair_invoke_called"):
                meta["repair_invoke_called"] = True
            if repair_extra.get("advisor_reason_code"):
                meta["advisor_reason_code"] = str(repair_extra.get("advisor_reason_code"))
            if repair_extra.get("advisor_repair_json_mode_error"):
                meta["advisor_repair_json_mode_error"] = str(repair_extra.get("advisor_repair_json_mode_error"))
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
        if structured_error:
            meta["advisor_structured_error"] = structured_error
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
            "advisor_parse_error": parse_error,
            **initial_diag,
            **repair_diag,
        }
    except Exception as exc:
        text = locals().get("text", "")
        repair_text = locals().get("repair_text", "")
        parse_error = locals().get("parse_error", {})
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
                "advisor_parse_error": parse_error,
                **diagnostics,
                **repair_diagnostics,
            },
            **diagnostics,
            **repair_diagnostics,
        }
