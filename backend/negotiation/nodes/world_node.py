from __future__ import annotations

import json
import os
import time

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
  "degrade_reason":string
}
Regla dura: si plan_status es advance_step o completed debe existir evidence no vacía.
Si no hay evidencia suficiente para avanzar/completar, usa continue_same_step.
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
    }


def world_judge_llm(
    *,
    active_plan: dict | None,
    user_message: str,
    objective: str,
    world_state: dict,
    recent_history: str,
    turn_count: int,
) -> tuple[dict, dict]:
    current_step = None
    if isinstance(active_plan, dict):
        steps = list(active_plan.get("steps", []))
        cur = int(active_plan.get("current_step_idx", 0) or 0)
        if steps:
            cur = max(0, min(cur, len(steps) - 1))
            if isinstance(steps[cur], dict):
                current_step = steps[cur]
    payload = {
        "turn_idx": turn_count,
        "objective": str(objective or "")[:240],
        "active_plan": active_plan if isinstance(active_plan, dict) else None,
        "current_step": current_step,
        "user_message": str(user_message or "")[:1000],
        "recent_history": str(recent_history or "")[-1200:],
        "world_state_summary": {
            "world_buckets": (world_state or {}).get("world_buckets", {}),
            "world_state_meta": (world_state or {}).get("world_state_meta", {}),
        },
    }

    started = time.perf_counter()
    try:
        model = get_planner_llm()
        messages = [
            SystemMessage(content=_WORLD_JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        raw = model.invoke(messages)
        text = getattr(raw, "content", str(raw))
        candidate = json.loads(text)
        normalized = _normalize_judgement(candidate, active_plan=active_plan, turn_count=turn_count)
        if normalized is None:
            raise ValueError("judge_invalid_json_shape")
        return normalized, {
            "judge_error_type": "",
            "judge_retry_count": 0,
            "judge_latency_ms": int((time.perf_counter() - started) * 1000),
            "judge_degraded": bool(normalized.get("degraded", False)),
        }
    except Exception as exc:
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
    if world_skipped:
        gate_state["world_skip_count"] = int(gate_state.get("world_skip_count", 0) or 0) + 1
        world_state, fallback_meta = apply_world_skip_fallback(prev_world, user_message, turn_count=turn_count)
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, world_state)
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
        state["world_diff"] = diff_world_state(prev_world, state["world_state"])
        extractor_meta["world_gate_features"] = gate_meta
        extractor_meta["extractor_skipped"] = False
        extractor_meta["interaction_updated"] = True
        state["extractor_meta"] = extractor_meta

    progress_state = update_conversation_mode(progress_state, state.get("world_state", {}), turn_count)
    active_plan = progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None
    judgement, judge_meta = world_judge_llm(
        active_plan=active_plan,
        user_message=user_message,
        objective=state.get("objective", ""),
        world_state=state.get("world_state", {}),
        recent_history=state.get("recent_history_text", ""),
        turn_count=turn_count,
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
