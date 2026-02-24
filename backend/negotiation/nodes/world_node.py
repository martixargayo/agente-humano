from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
import os
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from ..gate_utils import (
    gate_world,
    input_shape_features,
    interaction_fingerprint,
    state_meta_fingerprint,
)
from ..llm_clients import get_planner_llm
from ..mode_inference import update_conversation_mode
from ..llm_background import (
    build_background_context,
    build_background_public_block,
    canonical_speaker_for_turn,
)
from ..perception.interaction_signals import _previous_user_message, extract_interaction_signals
from ..schemas import default_progress_state, default_world_state
from ..world_state_updater import apply_world_skip_fallback, diff_world_state, update_world_state
from ..telemetry.trace_runtime import record_gate_event, record_llm_call_ms, record_node_phase_ms
from ..telemetry.llm_usage import extract_llm_usage
from ..advisor import build_advisor_recs
from ..llm_planning_context import (
    build_full_roleplay_profiles,
    build_judge_context_block_full,
    build_objective_summary,
    build_world_digest,
    build_world_full_compact,
    compact_json_for_prompt,
)
from ..repo_prompts import WORLD_JUDGE_V2_SYSTEM_PROMPT, WORLD_JUDGE_V2_USER_PROMPT


_PENDING_PARALLEL_LOCK = threading.Lock()
_PENDING_PARALLEL: dict[str, dict] = {}


def _store_pending_parallel(payload: dict) -> str:
    key = f"wp-{uuid4()}"
    with _PENDING_PARALLEL_LOCK:
        _PENDING_PARALLEL[key] = payload
    return key


def _pop_pending_parallel(key: str) -> dict | None:
    with _PENDING_PARALLEL_LOCK:
        return _PENDING_PARALLEL.pop(key, None)




def _append_trace_debug_marker(state: dict, marker: str, **extra: object) -> None:
    markers = state.get("trace_debug_markers")
    if not isinstance(markers, list):
        markers = []
    payload = {"marker": marker, "ts": datetime.now(timezone.utc).isoformat()}
    payload.update({k: v for k, v in extra.items() if v is not None})
    markers.append(payload)
    state["trace_debug_markers"] = markers[-64:]
def _compute_parallelism_metrics(state: dict, parallel_meta: dict) -> None:
    calls_by_name = {
        item.get("name"): item
        for item in (
            state.get("trace_runtime", {}).get("llm_calls", []) if isinstance(state.get("trace_runtime"), dict) else []
        )
        if isinstance(item, dict)
    }
    task_names = ["world_extractor_llm", "world_judge_llm", "advisor_llm"]
    latencies = []
    for task in task_names:
        call = calls_by_name.get(task, {})
        task_latency = int(call.get("latency_ms", 0) or 0)
        if task == "advisor_llm" and str(call.get("status", "")) == "skipped":
            task_latency = 0
        parallel_meta.setdefault("tasks", {})[task] = {
            "started_at": str(call.get("start_ts", "") or ""),
            "ended_at": str(call.get("end_ts", "") or ""),
            "latency_ms": task_latency,
            "status": str(call.get("status", "") or ""),
        }
        latencies.append(task_latency)
    sum_ms = sum(latencies)
    critical_path_ms = max(latencies) if latencies else 0
    overlap_ms = max(0, sum_ms - critical_path_ms)
    parallel_meta["sum_ms"] = sum_ms
    parallel_meta["critical_path_ms"] = critical_path_ms
    parallel_meta["overlap_ms"] = overlap_ms
    parallel_meta["saved_ms_estimate"] = overlap_ms
    state["world_parallelism"] = parallel_meta
    _append_trace_debug_marker(state, "world_parallelism_written_to_state", enabled=parallel_meta.get("enabled"), overlap_ms=parallel_meta.get("overlap_ms"))


def _apply_judge_advisor_results(
    state: dict,
    *,
    parallel_meta: dict,
    judgement: dict,
    judge_meta: dict,
    advisor_recs: dict,
    advisor_meta: dict,
) -> None:
    if bool(advisor_meta.get("advisor_llm_called", False)):
        record_llm_call_ms(
            state,
            name="advisor_llm",
            node="world_updater",
            latency_ms=int(advisor_meta.get("advisor_latency_ms", 0) or 0),
            ok=bool(advisor_meta.get("advisor_ok", False)),
            model=advisor_meta.get("advisor_model"),
            retry_count=0,
            error_stage=str(advisor_meta.get("advisor_error_stage") or ("llm_invoke" if advisor_meta.get("advisor_error") else "")),
            error=str(advisor_meta.get("advisor_error", "")),
            start_ts=advisor_meta.get("advisor_start_ts"),
            end_ts=advisor_meta.get("advisor_end_ts"),
            input_prompt_rendered=str(advisor_meta.get("advisor_input_prompt_rendered", "")),
            output_text_rendered=str(advisor_meta.get("advisor_output_text_rendered", "")),
            input_payload_raw=advisor_meta.get("advisor_input_payload_raw"),
            output_payload_raw=advisor_meta.get("advisor_output_payload_raw"),
            prompt_variant=advisor_meta.get("advisor_prompt_variant"),
            payload_chars=advisor_meta.get("advisor_payload_chars"),
            llm_call_count=advisor_meta.get("advisor_llm_call_count"),
        )
    else:
        now_iso = datetime.now(timezone.utc).isoformat()
        disabled = str(advisor_meta.get("advisor_error", "")).strip().lower() == "disabled"
        start_iso = str(advisor_meta.get("advisor_start_ts") or advisor_meta.get("advisor_scheduled_start_ts") or now_iso)
        end_iso = str(advisor_meta.get("advisor_end_ts") or now_iso)
        advisor_error = str(
            advisor_meta.get("advisor_error")
            or advisor_meta.get("advisor_error_message")
            or "advisor_not_called"
        )
        advisor_error_type = str(advisor_meta.get("advisor_error_type") or "")
        advisor_error_stage = str(advisor_meta.get("advisor_error_stage") or ("disabled" if disabled else "llm_invoke"))
        record_llm_call_ms(
            state,
            name="advisor_llm",
            node="world_updater",
            latency_ms=0,
            ok=False if disabled else False,
            status="skipped" if disabled else "error",
            error_stage=advisor_error_stage,
            error="disabled_by_config" if disabled else advisor_error,
            start_ts=start_iso,
            end_ts=end_iso,
            input_payload_raw=advisor_meta.get("advisor_input_payload_raw"),
            output_payload_raw=advisor_meta.get("advisor_output_payload_raw")
            if advisor_meta.get("advisor_output_payload_raw") is not None
            else {
                "error_type": advisor_error_type or ("disabled" if disabled else "advisor_not_called"),
                "error_message": "disabled_by_config" if disabled else advisor_error,
                "stage": advisor_error_stage,
            },
        )

    state["advisor_recs"] = advisor_recs
    state["advisor_meta"] = advisor_meta

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
        error_stage=str(judge_meta.get("judge_error_stage", "") or ("llm_exception" if judge_meta.get("judge_error_type") else "")),
        error=str(judge_meta.get("judge_error_type", "")),
        start_ts=judge_meta.get("judge_start_ts"),
        end_ts=judge_meta.get("judge_end_ts"),
        queue_ms=judge_meta.get("judge_queue_ms"),
        ttfb_ms=judge_meta.get("judge_ttfb_ms"),
        input_prompt_rendered=str(judge_meta.get("judge_input_prompt_rendered", "")),
        output_text_rendered=str(judge_meta.get("judge_output_text_rendered", "")),
        input_payload_raw=judge_meta.get("judge_input_payload_raw"),
        output_payload_raw=judge_meta.get("judge_output_payload_raw"),
        prompt_variant=judge_meta.get("judge_prompt_variant"),
        payload_chars=judge_meta.get("judge_payload_chars"),
        llm_call_count=judge_meta.get("judge_llm_call_count"),
    )

    extractor_meta = state.get("extractor_meta") if isinstance(state.get("extractor_meta"), dict) else {}
    extractor_reason_codes = []
    for bucket in list(extractor_meta.get("updated_buckets", []) if isinstance(extractor_meta, dict) else []):
        if str(bucket) in {"offers", "requests", "constraints", "interests"}:
            extractor_reason_codes.append(f"world_updated:{bucket}")
    judge_meta["inputs_world_version"] = "prev_world"
    advisor_meta["inputs_world_version"] = "prev_world"
    judge_meta["judge_may_be_stale_due_to_world_update"] = bool(extractor_reason_codes)
    advisor_meta["advisor_may_be_stale_due_to_world_update"] = bool(extractor_reason_codes)
    judge_meta["staleness_reason_codes"] = extractor_reason_codes
    advisor_meta["staleness_reason_codes"] = extractor_reason_codes

    state["policy_plan_judgement"] = judgement
    judge_meta["missing_signals"] = list(judgement.get("missing_signals", []))[:6]
    judge_meta["safety_flags"] = list(judgement.get("safety_flags", []))[:6]
    state.setdefault("extractor_meta", {})["world_judge_meta"] = judge_meta

    world_debug = state.get("world_debug") if isinstance(state.get("world_debug"), dict) else {}
    world_debug["policy_plan_judgement"] = judgement
    world_debug["world_judge_meta"] = judge_meta
    state["world_debug"] = world_debug
    _compute_parallelism_metrics(state, parallel_meta)


def flush_world_parallel_pending(state: dict) -> dict:
    _append_trace_debug_marker(state, "flush_started_at")
    pending = state.pop("_pending_world_parallel", None)
    pending_key = str(state.pop("world_parallel_pending_key", "") or "")
    if not isinstance(pending, dict) and pending_key:
        pending = _pop_pending_parallel(pending_key)
    if not isinstance(pending, dict):
        _append_trace_debug_marker(state, "flush_completed_at", had_pending=False)
        return state

    parallel_meta = pending.get("parallel_meta") if isinstance(pending.get("parallel_meta"), dict) else {}
    parallel_started_ts = str(pending.get("parallel_started_ts", "") or "")
    advisor_enabled = bool(pending.get("advisor_enabled", True))
    judgement = pending.get("judgement") if isinstance(pending.get("judgement"), dict) else None
    judge_meta = pending.get("judge_meta") if isinstance(pending.get("judge_meta"), dict) else None
    advisor_recs = pending.get("advisor_recs") if isinstance(pending.get("advisor_recs"), dict) else None
    advisor_meta = pending.get("advisor_meta") if isinstance(pending.get("advisor_meta"), dict) else None

    executor = pending.get("executor")
    judge_future = pending.get("judge_future") if isinstance(pending.get("judge_future"), Future) else None
    advisor_future = pending.get("advisor_future") if isinstance(pending.get("advisor_future"), Future) else None

    judge_join_error = None
    advisor_join_error = None
    try:
        if judge_future is not None:
            try:
                judgement, judge_meta = judge_future.result()
            except Exception as exc:
                judge_join_error = exc
                parallel_meta["fallback_to_sequential"] = True
                parallel_meta.setdefault("fallback_reason_codes", []).append("parallel_join_error:judge")
        if advisor_enabled and advisor_future is not None:
            try:
                advisor_recs, advisor_meta = advisor_future.result()
            except Exception as exc:
                advisor_join_error = exc
                parallel_meta["fallback_to_sequential"] = True
                parallel_meta.setdefault("fallback_reason_codes", []).append("parallel_join_error:advisor")
    finally:
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)

    if not isinstance(judgement, dict):
        judgement = {"plan_status": "interrupted_replan", "missing_signals": [], "safety_flags": []}
    if not isinstance(judge_meta, dict):
        judge_meta = {
            "judge_error_type": (judge_join_error.__class__.__name__ if judge_join_error else "join_error"),
            "judge_latency_ms": 0,
            "judge_start_ts": parallel_started_ts or datetime.now(timezone.utc).isoformat(),
            "judge_end_ts": datetime.now(timezone.utc).isoformat(),
            "judge_error_message": str(judge_join_error)[:180] if judge_join_error else "join_error",
        }
    if not isinstance(advisor_recs, dict):
        advisor_recs = {}
    if not isinstance(advisor_meta, dict):
        advisor_meta = {
            "advisor_ok": False,
            "advisor_latency_ms": 0,
            "advisor_error": str(advisor_join_error)[:180] if advisor_join_error else "join_error",
            "advisor_error_type": advisor_join_error.__class__.__name__ if advisor_join_error else "join_error",
            "advisor_llm_called": False,
            "advisor_start_ts": parallel_started_ts or datetime.now(timezone.utc).isoformat(),
            "advisor_end_ts": datetime.now(timezone.utc).isoformat(),
        }

    _apply_judge_advisor_results(
        state,
        parallel_meta=parallel_meta,
        judgement=judgement,
        judge_meta=judge_meta,
        advisor_recs=advisor_recs,
        advisor_meta=advisor_meta,
    )
    _append_trace_debug_marker(state, "flush_completed_at", had_pending=True)
    return state


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
    state: dict | None = None,
) -> tuple[dict, dict]:
    current_step = None
    success_criteria_list: list[str] = []
    if isinstance(active_plan, dict):
        steps = list(active_plan.get("steps", []))
        cur = int(active_plan.get("current_step_idx", 0) or 0)
        if steps:
            cur = max(0, min(cur, len(steps) - 1))
            if isinstance(steps[cur], dict):
                current_step = steps[cur]
                raw_sc = (current_step or {}).get("success_criteria")
                if isinstance(raw_sc, list):
                    success_criteria_list = [str(x).strip() for x in raw_sc if str(x).strip()]
                elif isinstance(raw_sc, str) and raw_sc.strip():
                    success_criteria_list = [raw_sc.strip()]
    progress_state = progress_state or {}
    world_diff = progress_state.get("world_diff") if isinstance(progress_state.get("world_diff"), dict) else {}
    evidence_candidates = _build_evidence_candidates(
        str(user_message or ""),
        str(assistant_last_message or ""),
        str(recent_history or ""),
    )
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
        "evidence_candidates": evidence_candidates,
        "world_state_summary": {
            "world_buckets": (world_state or {}).get("world_buckets", {}),
            "world_state_meta": (world_state or {}).get("world_state_meta", {}),
        },
    }

    started = time.perf_counter()
    started_wall = datetime.now(timezone.utc).isoformat()
    use_v2 = True
    model_name = None
    text = ""
    rendered_prompt = ""
    try:
        model = get_planner_llm()
        model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
        if use_v2:
            persona_profile, scene_profile, style_contract, constraints_struct = build_full_roleplay_profiles(progress_state)
            full_profiles_block = build_judge_context_block_full(progress_state)
            objective_summary = build_objective_summary(objective, scene_profile, persona_profile)
            speaker_of_last_message = canonical_speaker_for_turn(
                progress_state=progress_state,
                state=state,
                default="seller",
            )
            world_digest_json = json.dumps(build_world_digest(world_state or {}, world_diff), ensure_ascii=False)
            user_prompt = WORLD_JUDGE_V2_USER_PROMPT.format(
                full_profiles_block=full_profiles_block,
                objective_summary=objective_summary,
                speaker_of_last_message=speaker_of_last_message,
                active_plan_json=json.dumps(active_plan if isinstance(active_plan, dict) else {}, ensure_ascii=False),
                current_step_json=json.dumps(current_step or {}, ensure_ascii=False),
                success_criteria_json=json.dumps(success_criteria_list, ensure_ascii=False),
                user_message=json.dumps(str(user_message or "")[:1000], ensure_ascii=False),
                assistant_last_message=json.dumps(str(assistant_last_message or "")[:1000], ensure_ascii=False),
                recent_history_text=json.dumps(str(recent_history or "")[-1200:], ensure_ascii=False),
                memory_short=json.dumps(str(memory_short or "")[-1200:], ensure_ascii=False),
                memory_long=json.dumps(str(memory_long or "")[-1200:], ensure_ascii=False),
                world_digest_json=world_digest_json,
                world_full_json=compact_json_for_prompt(build_world_full_compact(world_state or {}), max_chars=8000),
                progress_counters_json=json.dumps(payload["progress_counters"], ensure_ascii=False),
                evidence_candidates_json=json.dumps(evidence_candidates, ensure_ascii=False),
            )
            messages = [
                SystemMessage(content=WORLD_JUDGE_V2_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        else:
            messages = [
                SystemMessage(content=_WORLD_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        rendered_prompt = "\n\n".join(
            f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
        )
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
        if use_v2 and speaker_of_last_message == "unknown":
            normalized["degraded"] = True
            normalized["degrade_reason"] = "missing_speaker_role"
            normalized["skip_planner"] = False
            original_why = str(normalized.get("why", "") or "")
            prefix = "Falta rol del hablante; decisión conservadora. "
            if not original_why.startswith(prefix):
                normalized["why"] = f"{prefix}{original_why}".strip()
            if normalized.get("plan_status") != "interrupted_replan":
                normalized["plan_status"] = "continue_same_step"
        return normalized, {
            "judge_error_type": "",
            "judge_error_stage": "",
            "judge_retry_count": 0,
            "judge_llm_call_count": 1,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": bool(normalized.get("degraded", False)),
            "judge_start_ts": started_wall,
            "judge_end_ts": ended_wall,
            "judge_model": llm_usage.get("model") or model_name,
            "judge_tokens_in": llm_usage.get("tokens_in"),
            "judge_tokens_out": llm_usage.get("tokens_out"),
            "judge_queue_ms": llm_usage.get("queue_ms"),
            "judge_ttfb_ms": llm_usage.get("ttfb_ms"),
            "judge_input_payload_raw": [
                {"role": getattr(msg, "type", "user"), "content": str(getattr(msg, "content", ""))}
                for msg in messages
            ],
            "judge_input_prompt_rendered": "\n\n".join(
                f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
            ),
            "judge_output_text_rendered": str(text),
            "judge_output_payload_raw": candidate,
            "judge_prompt_variant": "v2" if use_v2 else "v1",
            "use_world_judge_v2": bool(use_v2),
            "judge_payload_chars": len(
                "\n\n".join(
                    f"[{getattr(msg, 'type', 'user')}]\n{str(getattr(msg, 'content', ''))}" for msg in messages
                )
            ),
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
        error_stage = "llm_exception"
        if isinstance(exc, json.JSONDecodeError):
            error_stage = "parse_failed"
        elif isinstance(exc, ValueError) and "judge_invalid_json_shape" in str(exc):
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
            "judge_prompt_variant": "v2" if use_v2 else "v1",
            "use_world_judge_v2": bool(use_v2),
            "judge_model": model_name,
            "judge_input_prompt_rendered": rendered_prompt,
            "judge_output_text_rendered": str(text),
            "judge_payload_chars": len(rendered_prompt),
        }


def world_updater_node(state: dict) -> dict:
    _append_trace_debug_marker(state, "world_updater_entered")
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
    gate_started_ts = datetime.now(timezone.utc).isoformat()
    world_skipped, skip_reason, gate_meta = gate_world(
        user_message=user_message,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_world_refresh_turn", 0) or 0),
        prev_features=gate_state.get("input_shape_prev") or {},
        current_features=current_features,
        interaction_fingerprint_prev=gate_state.get("interaction_fingerprint_prev"),
        interaction_fingerprint_current=interaction_fingerprint_current,
        interaction_fingerprint_version=int(gate_state.get("interaction_fingerprint_version", 1) or 1),
        interval=int(os.getenv("WORLD_REFRESH_INTERVAL_TURNS", "3")),
        modality=modality,
        conversation_mode=conversation_mode,
    )
    gate_ended_ts = datetime.now(timezone.utc).isoformat()
    record_node_phase_ms(state, "world_updater", "gates_ms", int((time.perf_counter() - gate_started) * 1000))
    record_gate_event(
        state,
        name="world_gate",
        node="world_updater",
        decision="skipped" if world_skipped else "executed",
        reason=skip_reason,
        reason_codes=[skip_reason] if skip_reason else [],
        gate_inputs={
            "modality": modality,
            "conversation_mode": conversation_mode,
            "user_message_empty": not bool((user_message or "").strip()),
            "interaction_fingerprint_version": int(gate_state.get("interaction_fingerprint_version", 1) or 1),
            "prev_features": gate_state.get("input_shape_prev") or {},
            "current_features": current_features,
        },
        gate_rule_id="gate_world",
        gate_version="v1",
        started=gate_started,
        started_ts=gate_started_ts,
        ended_ts=gate_ended_ts,
    )

    normalize_started = time.perf_counter()
    world_local_timers: dict[str, int] = {}

    parallel_enabled = os.getenv("WORLD_PARALLELISM_ENABLED", "1") == "1"
    advisor_enabled = os.getenv("ADVISOR_ENABLED", "1") == "1"
    parallel_meta = {
        "enabled": bool(parallel_enabled),
        "mode": "threads" if parallel_enabled else "n/a",
        "tasks": {},
        "fallback_to_sequential": False,
        "fallback_reason_codes": [],
        "sum_ms": 0,
        "critical_path_ms": 0,
        "overlap_ms": 0,
        "saved_ms_estimate": 0,
    }
    state["world_parallelism"] = dict(parallel_meta)

    def _run_extractor() -> tuple[dict, dict, dict]:
        if world_skipped:
            ws, fallback_meta = apply_world_skip_fallback(prev_world, user_message, turn_count=turn_count)
            extractor_meta_local = {
                "extractor_used": False,
                "extractor_skipped": True,
                "skip_reason": skip_reason,
                "world_gate_features": gate_meta,
                "interaction_updated": True,
                **fallback_meta,
            }
            wd = {} if prev_world == ws else diff_world_state(prev_world, ws)
            return ws, wd, extractor_meta_local
        persona_profile, scene_profile, style_contract, constraints_struct = build_background_context(progress_state)
        speaker_of_user_message = canonical_speaker_for_turn(
            progress_state=progress_state,
            state=state,
            default="seller",
        )
        background_block_public = build_background_public_block(
            persona_profile,
            scene_profile,
            style_contract,
            constraints_struct,
            language="es",
            task_type="negotiation",
            domain="mustang67_car_purchase",
            participants={"buyer": "Carlos", "seller": "Don Joaquín"},
            speaker_of_user_message=speaker_of_user_message,
        )
        active_plan = progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else {}
        plan_steps = list(active_plan.get("steps") or []) if isinstance(active_plan, dict) else []
        step_idx = int(active_plan.get("current_step_idx", 0) or 0) if isinstance(active_plan, dict) else 0
        current_step = plan_steps[step_idx] if plan_steps and 0 <= step_idx < len(plan_steps) and isinstance(plan_steps[step_idx], dict) else {}
        success_criteria = current_step.get("success_criteria") if isinstance(current_step.get("success_criteria"), list) else []
        expected_slots = active_plan.get("slots_required") if isinstance(active_plan.get("slots_required"), list) else []
        policy_plan_judgement = state.get("policy_plan_judgement") if isinstance(state.get("policy_plan_judgement"), dict) else {}
        missing_signals = policy_plan_judgement.get("missing_signals") if isinstance(policy_plan_judgement.get("missing_signals"), list) else []

        ws, extractor_meta_local = update_world_state(
            prev_world,
            user_message,
            recent_history=state.get("recent_history_text", ""),
            belief_state=state.get("belief_state") or {},
            turn_count=turn_count,
            conversation_mode=conversation_mode,
            deps=deps,
            speaker_of_user_message=speaker_of_user_message,
            persona_profile=persona_profile,
            scene_profile=scene_profile,
            style_contract=style_contract,
            constraints_struct=constraints_struct,
            background_block_public=background_block_public,
            last_assistant_question=state.get("last_assistant_message", ""),
            current_step_micro_goal=str(current_step.get("micro_goal", "") or ""),
            success_criteria=[str(x)[:120] for x in success_criteria if str(x).strip()][:6],
            missing_signals=[str(x)[:120] for x in missing_signals if str(x).strip()][:6],
            expected_slots=[str(x)[:120] for x in expected_slots if str(x).strip()][:6],
        )
        extractor_meta_local["world_gate_features"] = gate_meta
        extractor_meta_local["extractor_skipped"] = False
        extractor_meta_local["interaction_updated"] = True
        wd = {} if prev_world == ws else diff_world_state(prev_world, ws)
        return ws, wd, extractor_meta_local

    # Design choice (Option A): judge/advisor use previous world snapshot to enable parallelism.
    def _run_judge() -> tuple[dict, dict]:
        return world_judge_llm(
            active_plan=progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None,
            user_message=user_message,
            objective=state.get("objective", ""),
            world_state=prev_world,
            recent_history=state.get("recent_history_text", ""),
            turn_count=turn_count,
            assistant_last_message=state.get("last_assistant_message", ""),
            memory_short=state.get("short_memory", ""),
            memory_long=state.get("long_memory", ""),
            progress_state=progress_state,
            state=state,
        )

    def _run_advisor() -> tuple[dict, dict]:
        if not advisor_enabled:
            return {}, {
                "advisor_ok": False,
                "advisor_latency_ms": 0,
                "advisor_error": "disabled",
                "advisor_llm_called": False,
            }
        return build_advisor_recs(
            objective=state.get("objective", ""),
            recent_history=state.get("recent_history_text", ""),
            memory_short=state.get("short_memory", ""),
            memory_long=state.get("long_memory", ""),
            active_plan=progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None,
            progress_state=progress_state,
            world_state=prev_world,
            belief_state=state.get("belief_state", {}),
            user_message=state.get("user_message", ""),
            state=state,
        )

    judgement: dict | None = None
    judge_meta: dict | None = None
    advisor_recs: dict | None = None
    advisor_meta: dict | None = None
    if parallel_enabled:
        try:
            executor = ThreadPoolExecutor(max_workers=3 if advisor_enabled else 2)
            parallel_started_ts = datetime.now(timezone.utc).isoformat()
            _append_trace_debug_marker(state, "world_parallel_scheduled_at", advisor_enabled=advisor_enabled)
            judge_future = executor.submit(_run_judge)
            advisor_future = executor.submit(_run_advisor) if advisor_enabled else None
            world_state, world_diff, extractor_meta = _run_extractor()
            pending_payload = {
                "executor": executor,
                "judge_future": judge_future,
                "advisor_future": advisor_future,
                "advisor_enabled": advisor_enabled,
                "parallel_meta": parallel_meta,
                "parallel_started_ts": parallel_started_ts,
            }
            state["_pending_world_parallel"] = pending_payload
            state["world_parallel_pending_key"] = _store_pending_parallel(pending_payload)
            _append_trace_debug_marker(state, "pending_payload_stored")
            if not advisor_enabled:
                advisor_recs, advisor_meta = _run_advisor()
        except Exception:
            parallel_meta["fallback_to_sequential"] = True
            parallel_meta["fallback_reason_codes"] = ["parallel_executor_error"]
            world_state, world_diff, extractor_meta = _run_extractor()
            advisor_recs, advisor_meta = _run_advisor()
            judgement, judge_meta = _run_judge()
    else:
        parallel_meta["fallback_to_sequential"] = True
        parallel_meta["fallback_reason_codes"] = ["parallel_disabled"]
        world_state, world_diff, extractor_meta = _run_extractor()
        advisor_recs, advisor_meta = _run_advisor()
        judgement, judge_meta = _run_judge()

    if world_skipped:
        gate_state["world_skip_count"] = int(gate_state.get("world_skip_count", 0) or 0) + 1
    else:
        gate_state["last_world_refresh_turn"] = turn_count

    state["world_state"] = world_state
    state["world_diff"] = world_diff
    state["extractor_meta"] = extractor_meta

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
            input_prompt_rendered=str(extractor_meta.get("extractor_input_prompt_rendered", "")),
            output_text_rendered=str(extractor_meta.get("extractor_output_text_rendered", "")),
            input_payload_raw=extractor_meta.get("extractor_input_payload_raw"),
            output_payload_raw=extractor_meta.get("extractor_output_payload_raw"),
        )

    progress_state = update_conversation_mode(progress_state, state.get("world_state", {}), turn_count)

    if not parallel_enabled or judgement is not None:
        _apply_judge_advisor_results(
            state,
            parallel_meta=parallel_meta,
            judgement=judgement or {},
            judge_meta=judge_meta or {},
            advisor_recs=advisor_recs or {},
            advisor_meta=advisor_meta or {},
        )
    else:
        if not advisor_enabled:
            state["advisor_recs"] = advisor_recs or {}
            state["advisor_meta"] = advisor_meta or {}
        _compute_parallelism_metrics(state, parallel_meta)

    normalize_total_ms = int((time.perf_counter() - normalize_started) * 1000)
    record_node_phase_ms(state, "world_updater", "normalize_merge_diff_ms", normalize_total_ms)
    world_local_timers.update((extractor_meta.get("timers") if isinstance(extractor_meta.get("timers"), dict) else {}))
    world_local_timers["normalize_merge_diff_total_ms"] = normalize_total_ms
    world_local_timers["prev_world_bytes"] = int(extractor_meta.get("prev_world_bytes", 0) or 0)
    world_local_timers["world_diff_bytes"] = int(extractor_meta.get("world_diff_bytes", 0) or 0)

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
        "policy_plan_judgement": state.get("policy_plan_judgement") or {},
        "world_judge_meta": (state.get("extractor_meta", {}).get("world_judge_meta") if isinstance(state.get("extractor_meta"), dict) else {}) or {},
        "timers": world_local_timers,
        "world_diff_bucket_summary": {
            "changed_buckets": changed[:12],
            "counts_delta": counts_delta,
        },
    }

    state["progress_state"] = progress_state
    state["conversation_mode"] = progress_state.get("conversation_mode", conversation_mode)
    gate_state["world_meta_fingerprint_prev"] = state_meta_fingerprint(state.get("world_state", {}).get("world_state_meta"))
    gate_state["input_shape_prev"] = current_features
    gate_state["last_interaction_signals"] = interaction_current
    gate_state["interaction_fingerprint_prev"] = interaction_fingerprint(interaction_current)
    gate_state["interaction_fingerprint_version"] = int(gate_state.get("interaction_fingerprint_version", 1) or 1)
    gate_state["prev_user_message"] = user_message
    state["progress_state"]["gate_state"] = gate_state
    return state
