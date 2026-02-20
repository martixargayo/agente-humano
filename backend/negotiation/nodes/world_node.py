from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from ..gate_utils import (
    gate_world,
    input_shape_features,
    interaction_fingerprint,
    state_meta_fingerprint,
)
from ..llm_clients import get_planner_llm
from ..mode_inference import update_conversation_mode
from ..perception.interaction_signals import _previous_user_message, extract_interaction_signals
from ..schemas import default_progress_state, default_world_state
from ..world_state_updater import apply_world_skip_fallback, diff_world_state, update_world_state
from ..telemetry.trace_runtime import record_llm_call_ms, record_node_phase_ms
from ..telemetry.llm_usage import extract_llm_usage
from ..advisor import build_advisor_recs


_WORLD_JUDGE_SYSTEM_PROMPT = """
Eres world_judge_llm. Evalúas el estado del plan activo y el último mensaje del usuario.
Devuelve SOLO JSON válido con schema v1:
{
  "schema_version":"v1",
  "turn_idx":int,
  "plan_presence":"active"|"none",
  "plan_id":string,
  "evaluated_step_idx":int,
  "plan_status":"continue_same_step"|"advance_step"|"completed"|"interrupted_replan",
  "why":string,
  "evidence":[{"quote":string,"source":string,"span":[int,int]}],
  "confidence":number,
  "missing_signals":[string],
  "safety_flags":[string],
  "degraded":boolean,
  "degrade_reason":string,
  "skip_planner":boolean
}
Reglas de auditabilidad de evidence:
- Si user_message o assistant_last_message tiene texto no vacío, evidence NO es opcional: devuelve al menos 1 evidencia literal.
- Selecciona 1 a 3 citas máximas; prioriza user_message y usa assistant_last_message/recent_history si justifican la decisión.
- Cada evidence debe justificar plan_status y, si hay missing_signals, debe mostrar por qué aún falta esa señal.
- continue_same_step también debe incluir evidence, salvo cuando no haya texto útil en user_message ni assistant_last_message.
- Para topic shift o interrupted_replan, cita explícitamente el fragmento que evidencia el cambio o bloqueo.
Regla dura: si plan_status es advance_step o completed debe existir evidence no vacía con confirmación explícita.
Si no hay evidencia suficiente para avanzar/completar, usa continue_same_step.
Regla de loop: si el mismo paso se repite sin progreso por varios turnos, considera interrupted_replan.
""".strip()


def _fallback_judgement(
    *,
    active_plan: dict | None,
    user_message: str,
    turn_count: int,
    degrade_reason: str,
) -> dict:
    text = (user_message or "").strip()
    evidence = (
        [{"quote": text[:180], "source": "user_message", "span": [0, min(len(text), 180)]}]
        if text
        else []
    )
    if not isinstance(active_plan, dict):
        return {
            "schema_version": "v1",
            "turn_idx": turn_count,
            "plan_presence": "none",
            "plan_id": "",
            "evaluated_step_idx": 0,
            "plan_status": "interrupted_replan",
            "why": "No hay plan activo; corresponde planificar.",
            "evidence": evidence,
            "confidence": 0.2,
            "missing_signals": [],
            "safety_flags": [],
            "degraded": True,
            "degrade_reason": degrade_reason or "judge_llm_failure_no_plan",
            "skip_planner": False,
        }

    plan_id = str(active_plan.get("plan_id", ""))[:40]
    steps = list(active_plan.get("steps", []))
    cur = int(active_plan.get("current_step_idx", 0) or 0)
    cur = max(0, min(cur, len(steps) - 1)) if steps else 0
    return {
        "schema_version": "v1",
        "turn_idx": turn_count,
        "plan_presence": "active",
        "plan_id": plan_id,
        "evaluated_step_idx": cur,
        "plan_status": "continue_same_step",
        "why": "Fallback degradado por fallo del world_judge_llm; se conserva el paso activo.",
        "evidence": evidence,
        "confidence": 0.2,
        "missing_signals": [],
        "safety_flags": [],
        "degraded": True,
        "degrade_reason": degrade_reason or "judge_llm_failure_with_plan",
        "skip_planner": False,
    }


def _normalize_judgement(candidate: object, *, active_plan: dict | None, turn_count: int) -> dict | None:
    if not isinstance(candidate, dict):
        return None
    plan_presence = "active" if isinstance(active_plan, dict) else "none"
    plan_id = str((candidate.get("plan_id") if isinstance(candidate, dict) else "") or "")[:40]
    if plan_presence == "none":
        plan_id = ""
    allowed_status = {"continue_same_step", "advance_step", "completed", "interrupted_replan"}
    status = str(candidate.get("plan_status", "continue_same_step")).strip()
    if status not in allowed_status:
        status = "continue_same_step"

    evidence = candidate.get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else []

    why = str(candidate.get("why", "")).strip() or "Judgement emitido por world_judge_llm."
    try:
        confidence = float(candidate.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    degraded = bool(candidate.get("degraded", False))
    degrade_reason = str(candidate.get("degrade_reason", "") or "")

    evaluated_step_idx = candidate.get("evaluated_step_idx", 0)
    try:
        evaluated_step_idx = max(0, int(evaluated_step_idx))
    except Exception:
        evaluated_step_idx = 0

    missing_signals = candidate.get("missing_signals", [])
    missing_signals = [str(x)[:120] for x in missing_signals if str(x).strip()] if isinstance(missing_signals, list) else []
    safety_flags = candidate.get("safety_flags", [])
    safety_flags = [str(x)[:80] for x in safety_flags if str(x).strip()] if isinstance(safety_flags, list) else []

    if status in {"advance_step", "completed"} and len(evidence) == 0:
        status = "continue_same_step"
        degraded = True
        degrade_reason = "missing_evidence_for_progress"

    skip_planner = bool(candidate.get("skip_planner", False))

    return {
        "schema_version": "v1",
        "turn_idx": turn_count,
        "plan_presence": plan_presence,
        "plan_id": plan_id,
        "evaluated_step_idx": evaluated_step_idx,
        "plan_status": status,
        "why": why[:280],
        "evidence": evidence[:4],
        "confidence": confidence,
        "missing_signals": missing_signals[:6],
        "safety_flags": safety_flags[:6],
        "degraded": degraded,
        "degrade_reason": degrade_reason[:80],
        "skip_planner": skip_planner,
    }


_ALLOWED_EVIDENCE_SOURCES = {"user_message", "assistant_last_message", "recent_history", "world_state"}


def _build_evidence_item(text: str, source: str, max_len: int = 180) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    quote = raw[:max_len]
    item = {"quote": quote, "source": source}
    if source in {"user_message", "assistant_last_message"}:
        item["span"] = [0, min(len(raw), max_len)]
    return item


def _build_evidence_candidates(user_message: str, assistant_last_message: str, recent_history: str) -> list[dict]:
    candidates: list[dict] = []
    user_item = _build_evidence_item(user_message, "user_message")
    if user_item:
        candidates.append(user_item)
    assistant_item = _build_evidence_item(assistant_last_message, "assistant_last_message")
    if assistant_item:
        candidates.append(assistant_item)
    recent_item = _build_evidence_item(str(recent_history or "")[:180], "recent_history")
    if recent_item:
        candidates.append(recent_item)
    return candidates[:3]


def _normalize_evidence_items(evidence: object) -> list[dict]:
    if not isinstance(evidence, list):
        return []
    normalized: list[dict] = []
    for item in evidence[:4]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", "") or "").strip()
        if not quote:
            continue
        source = str(item.get("source", "") or "").strip()
        if source not in _ALLOWED_EVIDENCE_SOURCES:
            source = "user_message"
        normalized_item = {"quote": quote[:180], "source": source}
        if source in {"user_message", "assistant_last_message"}:
            span = item.get("span")
            if isinstance(span, list) and len(span) == 2:
                try:
                    a = max(0, int(span[0]))
                    b = max(a, int(span[1]))
                    normalized_item["span"] = [a, min(180, b)]
                except Exception:
                    pass
        normalized.append(normalized_item)
    return normalized


def _has_text_for_audit(payload: dict) -> bool:
    return bool(str(payload.get("user_message", "") or "").strip() or str(payload.get("assistant_last_message", "") or "").strip())


def _evidence_shows_new_information(evidence: list[dict]) -> bool:
    return any(bool(str((it or {}).get("quote", "") or "").strip()) for it in evidence if isinstance(it, dict))


def _post_normalize_evidence_guardrails(
    judgement: dict,
    *,
    payload: dict,
    progress_state: dict | None,
) -> tuple[dict, dict]:
    normalized = dict(judgement)
    evidence = _normalize_evidence_items(normalized.get("evidence", []))
    missing_signals = normalized.get("missing_signals", [])
    missing_signals = missing_signals if isinstance(missing_signals, list) else []

    has_text = _has_text_for_audit(payload)
    needs_evidence = bool(has_text or missing_signals)
    injected = False

    if len(evidence) == 0 and needs_evidence:
        evidence = _build_evidence_candidates(
            str(payload.get("user_message", "") or ""),
            str(payload.get("assistant_last_message", "") or ""),
            str(payload.get("recent_history", "") or ""),
        )[:1]
        injected = len(evidence) > 0
        if injected:
            normalized["degraded"] = True
            if not str(normalized.get("degrade_reason", "") or "").strip():
                normalized["degrade_reason"] = "missing_evidence_required"

    status = str(normalized.get("plan_status", ""))
    if status in {"advance_step", "completed"} and len(evidence) == 0:
        evidence = _build_evidence_candidates(
            str(payload.get("user_message", "") or ""),
            str(payload.get("assistant_last_message", "") or ""),
            str(payload.get("recent_history", "") or ""),
        )[:1]
        injected = injected or len(evidence) > 0
        normalized["degraded"] = True
        normalized["degrade_reason"] = "missing_evidence_for_progress"

    if len(missing_signals) > 0 and len(evidence) == 0:
        evidence = _build_evidence_candidates(
            str(payload.get("user_message", "") or ""),
            str(payload.get("assistant_last_message", "") or ""),
            str(payload.get("recent_history", "") or ""),
        )[:1]
        injected = injected or len(evidence) > 0
        if len(evidence) > 0 and not str(normalized.get("degrade_reason", "") or "").strip():
            normalized["degraded"] = True
            normalized["degrade_reason"] = "missing_evidence_required"

    if "nueva_informacion_verificable" in missing_signals and _evidence_shows_new_information(evidence):
        missing_signals = [x for x in missing_signals if str(x) != "nueva_informacion_verificable"]

    normalized["evidence"] = evidence[:4]
    normalized["missing_signals"] = [str(x)[:120] for x in missing_signals if str(x).strip()][:6]

    no_progress_same_step_turns = int((progress_state or {}).get("no_progress_same_step_turns", 0) or 0)
    if normalized.get("plan_status") == "continue_same_step" and no_progress_same_step_turns >= 3:
        normalized["plan_status"] = "interrupted_replan"
        normalized["degraded"] = True
        normalized["degrade_reason"] = "loop_same_step_threshold"

    meta_flags = {
        "judge_evidence_missing": len(normalized.get("evidence", [])) == 0,
        "judge_evidence_injected": injected,
        "judge_evidence_sources": sorted({str((it or {}).get("source", "")) for it in normalized.get("evidence", []) if isinstance(it, dict) and str((it or {}).get("source", ""))}),
        "judge_missing_signals_without_evidence": bool(normalized.get("missing_signals")) and len(normalized.get("evidence", [])) == 0,
    }
    return normalized, meta_flags


def world_judge_llm(
    *,
    active_plan: dict | None,
    user_message: str,
    objective: str,
    world_state: dict,
    recent_history: str,
    turn_count: int,
    assistant_last_message: str = "",
    memory_short: str = "",
    memory_long: str = "",
    progress_state: dict | None = None,
) -> tuple[dict, dict]:
    current_step = None
    if isinstance(active_plan, dict):
        steps = list(active_plan.get("steps", []))
        cur = int(active_plan.get("current_step_idx", 0) or 0)
        if steps:
            cur = max(0, min(cur, len(steps) - 1))
            if isinstance(steps[cur], dict):
                current_step = steps[cur]
    progress_state = progress_state or {}
    payload = {
        "turn_idx": turn_count,
        "objective": str(objective or "")[:240],
        "active_plan": active_plan if isinstance(active_plan, dict) else None,
        "current_step": current_step,
        "user_message": str(user_message or "")[:1000],
        "assistant_last_message": str(assistant_last_message or "")[:1000],
        "recent_history": str(recent_history or "")[-1200:],
        "memory_short": str(memory_short or "")[-1200:],
        "memory_long": str(memory_long or "")[-1200:],
        "progress_counters": {
            "judgement_missing_streak": int(progress_state.get("judgement_missing_streak", 0) or 0),
            "no_progress_same_step_turns": int(progress_state.get("no_progress_same_step_turns", 0) or 0),
            "turns_in_same_mode": int(progress_state.get("turns_in_same_mode", 0) or 0),
            "plan_id_changes_window": int(progress_state.get("plan_id_changes_window", 0) or 0),
            "loop_flags": list(progress_state.get("loop_flags", []) or []),
        },
        "evidence_candidates": _build_evidence_candidates(
            str(user_message or ""),
            str(assistant_last_message or ""),
            str(recent_history or ""),
        ),
        "world_state_summary": {
            "world_buckets": (world_state or {}).get("world_buckets", {}),
            "world_state_meta": (world_state or {}).get("world_state_meta", {}),
        },
    }

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    try:
        model = get_planner_llm()
        messages = [
            SystemMessage(content=_WORLD_JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        raw = model.invoke(messages)
        ended_wall = datetime.now(timezone.utc).isoformat()
        llm_usage = extract_llm_usage(raw)
        text = getattr(raw, "content", str(raw))
        candidate = json.loads(text)
        normalized = _normalize_judgement(candidate, active_plan=active_plan, turn_count=turn_count)
        if normalized is None:
            raise ValueError("judge_invalid_json_shape")
        normalized, evidence_meta = _post_normalize_evidence_guardrails(
            normalized,
            payload=payload,
            progress_state=progress_state,
        )
        return normalized, {
            "judge_error_type": "",
            "judge_retry_count": 0,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": bool(normalized.get("degraded", False)),
            "judge_start_ts": started_wall,
            "judge_end_ts": ended_wall,
            "judge_model": llm_usage.get("model"),
            "judge_tokens_in": llm_usage.get("tokens_in"),
            "judge_tokens_out": llm_usage.get("tokens_out"),
            "judge_queue_ms": llm_usage.get("queue_ms"),
            "judge_ttfb_ms": llm_usage.get("ttfb_ms"),
            **evidence_meta,
        }
    except Exception as exc:
        ended_wall = datetime.now(timezone.utc).isoformat()
        fallback = _fallback_judgement(
            active_plan=active_plan,
            user_message=user_message,
            turn_count=turn_count,
            degrade_reason=str(exc)[:80] or "judge_llm_exception",
        )
        return fallback, {
            "judge_error_type": exc.__class__.__name__,
            "judge_retry_count": 1,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": True,
            "judge_start_ts": started_wall,
            "judge_end_ts": ended_wall,
        }


def world_updater_node(state: dict) -> dict:
    deps = state.get("deps")
    prev_world = state.get("world_state") or default_world_state()
    state["prev_world_state"] = prev_world
    progress_state = state.get("progress_state") or default_progress_state()
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    user_message = state.get("user_message", "")
    turn_count = state.get("turn_count", 0) or 0
    modality = state.get("input_modality", "text")
    conversation_mode = progress_state.get("conversation_mode", "general") or "general"
    state["conversation_mode"] = conversation_mode
    prev_text = gate_state.get("prev_user_message", "")
    recent_history = state.get("recent_history")
    if isinstance(recent_history, list):
        prev_text = _previous_user_message(recent_history) or prev_text
    current_features = input_shape_features(
        user_message,
        modality=modality,
        prev_text=prev_text,
        conversation_mode=conversation_mode,
    )
    interaction_current = extract_interaction_signals(
        user_message,
        prev_world,
        recent_history=state.get("recent_history_text", []),
        tone_signal=None,
        prev_interaction=gate_state.get("last_interaction_signals", {}),
    )
    interaction_fingerprint_current = interaction_fingerprint(interaction_current)
    gate_started = time.perf_counter()
    world_skipped, skip_reason, gate_meta = gate_world(
        user_message=user_message,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_world_refresh_turn", 0) or 0),
        prev_features=gate_state.get("input_shape_prev") or {},
        current_features=current_features,
        interaction_fingerprint_prev=gate_state.get("interaction_fingerprint_prev"),
        interaction_fingerprint_current=interaction_fingerprint_current,
        interaction_fingerprint_version=int(
            gate_state.get("interaction_fingerprint_version", 1) or 1
        ),
        interval=int(os.getenv("WORLD_REFRESH_INTERVAL_TURNS", "3")),
        modality=modality,
        conversation_mode=conversation_mode,
    )
    record_node_phase_ms(state, "world_updater", "gates_ms", int((time.perf_counter() - gate_started) * 1000))

    normalize_started = time.perf_counter()
    world_local_timers: dict[str, int] = {}
    if world_skipped:
        gate_state["world_skip_count"] = int(gate_state.get("world_skip_count", 0) or 0) + 1
        world_state, fallback_meta = apply_world_skip_fallback(prev_world, user_message, turn_count=turn_count)
        state["world_state"] = world_state
        state["world_diff"] = {} if prev_world == world_state else diff_world_state(prev_world, world_state)
        state["extractor_meta"] = {
            "extractor_used": False,
            "extractor_skipped": True,
            "skip_reason": skip_reason,
            "world_gate_features": gate_meta,
            "interaction_updated": True,
            **fallback_meta,
        }
    else:
        world_state, extractor_meta = update_world_state(
            prev_world,
            user_message,
            recent_history=state.get("recent_history_text", ""),
            belief_state=state.get("belief_state") or {},
            turn_count=turn_count,
            conversation_mode=conversation_mode,
            deps=deps,
        )
        gate_state["last_world_refresh_turn"] = turn_count
        state["world_state"] = world_state
        diff_started = time.perf_counter()
        state["world_diff"] = {} if prev_world == state["world_state"] else diff_world_state(prev_world, state["world_state"])
        world_local_timers["world_diff_ms"] = int((time.perf_counter() - diff_started) * 1000)
        extractor_meta["world_gate_features"] = gate_meta
        extractor_meta["extractor_skipped"] = False
        extractor_meta["interaction_updated"] = True
        state["extractor_meta"] = extractor_meta

    extractor_meta = state.get("extractor_meta", {}) if isinstance(state.get("extractor_meta"), dict) else {}
    extractor_latency_ms = int(extractor_meta.get("extractor_llm_latency_ms", 0) or 0)
    if extractor_latency_ms > 0:
        record_llm_call_ms(
            state,
            name="world_extractor_llm",
            node="world_updater",
            latency_ms=extractor_latency_ms,
            ok=not bool(extractor_meta.get("extractor_failed", False)),
            model=extractor_meta.get("extractor_llm_model"),
            tokens_in=extractor_meta.get("extractor_llm_tokens_in"),
            tokens_out=extractor_meta.get("extractor_llm_tokens_out"),
            retry_count=0,
            error_stage="llm_invoke" if extractor_meta.get("extractor_failed", False) else "",
            error=str(extractor_meta.get("error", "")),
            start_ts=str(extractor_meta.get("extractor_llm_start_ts", "") or ""),
            end_ts=str(extractor_meta.get("extractor_llm_end_ts", "") or ""),
            queue_ms=extractor_meta.get("extractor_llm_queue_ms"),
            ttfb_ms=extractor_meta.get("extractor_llm_ttfb_ms"),
        )

    normalize_total_ms = int((time.perf_counter() - normalize_started) * 1000)
    record_node_phase_ms(state, "world_updater", "normalize_merge_diff_ms", normalize_total_ms)
    world_local_timers.update((extractor_meta.get("timers") if isinstance(extractor_meta.get("timers"), dict) else {}))
    world_local_timers["normalize_merge_diff_total_ms"] = normalize_total_ms
    world_local_timers["prev_world_bytes"] = int(extractor_meta.get("prev_world_bytes", 0) or 0)
    world_local_timers["world_diff_bytes"] = int(extractor_meta.get("world_diff_bytes", 0) or 0)

    progress_state = update_conversation_mode(progress_state, state.get("world_state", {}), turn_count)
    active_plan = progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None
    if os.getenv("ADVISOR_ENABLED", "0") == "1":
        advisor_recs, advisor_meta = build_advisor_recs(
            objective=state.get("objective", ""),
            recent_history=state.get("recent_history_text", ""),
            memory_short=state.get("short_memory", ""),
            memory_long=state.get("long_memory", ""),
            active_plan=active_plan,
            progress_state=progress_state,
            world_state=state.get("world_state", {}),
            belief_state=state.get("belief_state", {}),
        )
        if bool(advisor_meta.get("advisor_llm_called", False)):
            record_llm_call_ms(
                state,
                name="advisor_llm",
                node="world_updater",
                latency_ms=int(advisor_meta.get("advisor_latency_ms", 0) or 0),
                ok=bool(advisor_meta.get("advisor_ok", False)),
                model=None,
                retry_count=0,
                error_stage="llm_invoke" if advisor_meta.get("advisor_error") else "",
                error=str(advisor_meta.get("advisor_error", "")),
            )
    else:
        advisor_recs, advisor_meta = {}, {"advisor_ok": False, "advisor_latency_ms": 0, "advisor_error": "disabled", "advisor_llm_called": False}
    state["advisor_recs"] = advisor_recs
    state["advisor_meta"] = advisor_meta
    judgement, judge_meta = world_judge_llm(
        active_plan=active_plan,
        user_message=user_message,
        objective=state.get("objective", ""),
        world_state=state.get("world_state", {}),
        recent_history=state.get("recent_history_text", ""),
        turn_count=turn_count,
        assistant_last_message=state.get("last_assistant_message", ""),
        memory_short=state.get("short_memory", ""),
        memory_long=state.get("long_memory", ""),
        progress_state=progress_state,
    )
    record_llm_call_ms(
        state,
        name="world_judge_llm",
        node="world_updater",
        latency_ms=int(judge_meta.get("judge_latency_ms", 0) or 0),
        ok=not bool(judge_meta.get("judge_error_type")),
        model=judge_meta.get("judge_model"),
        tokens_in=judge_meta.get("judge_tokens_in"),
        tokens_out=judge_meta.get("judge_tokens_out"),
        retry_count=int(judge_meta.get("judge_retry_count", 0) or 0),
        error_stage="llm_invoke" if judge_meta.get("judge_error_type") else "",
        error=str(judge_meta.get("judge_error_type", "")),
        start_ts=judge_meta.get("judge_start_ts"),
        end_ts=judge_meta.get("judge_end_ts"),
        queue_ms=judge_meta.get("judge_queue_ms"),
        ttfb_ms=judge_meta.get("judge_ttfb_ms"),
    )
    state["policy_plan_judgement"] = judgement
    judge_meta["missing_signals"] = list(judgement.get("missing_signals", []))[:6]
    judge_meta["safety_flags"] = list(judgement.get("safety_flags", []))[:6]
    state.setdefault("extractor_meta", {})["world_judge_meta"] = judge_meta

    prev_buckets = ((state.get("prev_world_state") or {}).get("world_buckets") or {}) if isinstance(state.get("prev_world_state"), dict) else {}
    curr_buckets = ((state.get("world_state") or {}).get("world_buckets") or {}) if isinstance(state.get("world_state"), dict) else {}
    bucket_names = sorted(set(prev_buckets.keys()) | set(curr_buckets.keys()))
    changed: list[str] = []
    counts_delta: dict[str, dict] = {}
    for bucket in bucket_names:
        b = prev_buckets.get(bucket, [])
        a = curr_buckets.get(bucket, [])
        b_count = len(b) if isinstance(b, list) else 0
        a_count = len(a) if isinstance(a, list) else 0
        if b_count != a_count or b != a:
            changed.append(bucket)
            counts_delta[bucket] = {"before": b_count, "after": a_count, "delta": a_count - b_count}
    state["world_debug"] = {
        "policy_plan_judgement": judgement,
        "world_judge_meta": judge_meta,
        "timers": world_local_timers,
        "world_diff_bucket_summary": {
            "changed_buckets": changed[:12],
            "counts_delta": counts_delta,
        },
    }

    state["progress_state"] = progress_state
    state["conversation_mode"] = progress_state.get("conversation_mode", conversation_mode)
    gate_state["world_meta_fingerprint_prev"] = state_meta_fingerprint(
        state.get("world_state", {}).get("world_state_meta")
    )
    gate_state["input_shape_prev"] = current_features
    gate_state["last_interaction_signals"] = interaction_current
    gate_state["interaction_fingerprint_prev"] = interaction_fingerprint(interaction_current)
    gate_state["interaction_fingerprint_version"] = int(
        gate_state.get("interaction_fingerprint_version", 1) or 1
    )
    gate_state["prev_user_message"] = user_message
    state["progress_state"]["gate_state"] = gate_state
    return state
