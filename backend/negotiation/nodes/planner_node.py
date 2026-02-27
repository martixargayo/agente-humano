from __future__ import annotations

import time
from datetime import datetime, timezone

from ..schemas import default_policy_decision, default_progress_state
from ..phase_map import get_phase_map_v1
from ..state.deps import DEFAULT_DEPS
from ..telemetry.trace_runtime import record_gate_event, record_llm_call
from ..semantic_ledger_utils import build_effective_semantic_ledger, semantic_ledger_hash


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def phase_policy_planner_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    progress_state = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else default_progress_state()
    state["phase_prev"] = str((((progress_state or {}).get("phase_state") or {}).get("phase")) or "clima_humano")

    effective_ledger = build_effective_semantic_ledger(
        progress_state,
        state.get("semantic_judge") if isinstance(state.get("semantic_judge"), dict) else {},
    )
    state["effective_semantic_ledger"] = effective_ledger
    state["effective_ledger_hash"] = semantic_ledger_hash(effective_ledger)

    state["assistant_last_message"] = state.get("assistant_last_message") or state.get("last_assistant_message") or ""

    gate_started = time.perf_counter()
    gate_started_ts = datetime.now(timezone.utc).isoformat()
    record_gate_event(
        state,
        name="planner_gate",
        node="phase_policy_planner",
        decision="executed",
        reason="semantic_planner_always_on",
        reason_codes=["semantic_planner_always_on"],
        gate_inputs={
            "semantic_ledger_present": isinstance(progress_state.get("semantic_ledger"), dict),
        },
        gate_rule_id="planner_semantic_v1",
        gate_version="v1",
        started=gate_started,
        started_ts=gate_started_ts,
    )

    started = time.perf_counter()
    planner_meta: dict = {}
    try:
        phase_candidate, policy_decision, planner_meta = deps.plan_phase_policy(
            world_state=state.get("world_state", {}),
            world_diff=state.get("world_diff", {}),
            belief_state=state.get("belief_state", {}),
            progress_state=progress_state,
            policy_state=progress_state.get("policy_state", {}),
            policy_plan_summary=None,
            objective=state.get("objective", ""),
            constraints=state.get("constraints", ""),
            constraints_struct=state.get("hard_constraints_struct", {}),
            recent_context=str(state.get("recent_history_text", "") or ""),
            advisor_recs=state.get("advisor_recs") if isinstance(state.get("advisor_recs"), dict) else {},
            judge_result=state.get("semantic_judge") if isinstance(state.get("semantic_judge"), dict) else {},
            memory_short=str(state.get("short_memory", "") or ""),
            memory_long=str(state.get("long_memory", "") or ""),
            user_message=str(state.get("user_message", "") or ""),
            assistant_last_message=str(state.get("assistant_last_message") or state.get("last_assistant_message") or ""),
            effective_semantic_ledger=effective_ledger,
        )
    except Exception as exc:
        phase_candidate = {
            "phase": "clima_humano",
            "confidence": 0.0,
            "reasons": ["planner_node_exception"],
            "signals": [],
            "alternatives": [],
        }
        policy_decision = default_policy_decision()
        planner_meta = {
            "planner_failed": True,
            "planner_fallback_used": True,
            "planner_error": str(exc),
            "planner_error_stage": "node_wrapper",
            "planner_semantic_output": {
                "schema_version": "planner_semantic_v1",
                "phase": "clima_humano",
                "style": "Breve y natural.",
                "next_move_hint": "Responder con calidez sin repetir temas ya tratados.",
                "what_not_to_repeat": [],
            },
        }

    record_llm_call(
        state,
        name="planner_llm",
        node="phase_policy_planner",
        started=started,
        ok=not bool(planner_meta.get("planner_failed", False)),
        model=planner_meta.get("planner_model"),
        tokens_in=planner_meta.get("planner_tokens_in"),
        tokens_out=planner_meta.get("planner_tokens_out"),
        retry_count=int(planner_meta.get("planner_retry_count", 0) or 0),
        error_stage=str(planner_meta.get("planner_error_stage", "")),
        error=str(planner_meta.get("planner_error", "")),
        input_prompt_rendered=str(planner_meta.get("planner_input_prompt_rendered", "")),
        output_text_rendered=str(planner_meta.get("planner_output_text_rendered", "")),
        input_payload_raw=planner_meta.get("planner_input_payload_raw"),
        output_payload_raw=planner_meta.get("planner_output_payload_raw"),
    )

    planner_semantic_output = planner_meta.get("planner_semantic_output") if isinstance(planner_meta.get("planner_semantic_output"), dict) else {
        "schema_version": "planner_semantic_v1",
        "phase": "clima_humano",
        "style": "Breve y natural.",
        "next_move_hint": "Responder con calidez sin insistir.",
        "what_not_to_repeat": [],
    }

    state["phase_candidate"] = phase_candidate
    state["phase_effective"] = {
        "phase": planner_semantic_output.get("phase", "clima_humano"),
        "phase_effective": planner_semantic_output.get("phase", "clima_humano"),
        "confidence": float((phase_candidate or {}).get("confidence", 0.7) or 0.7),
        "reasons": list((phase_candidate or {}).get("reasons", []) or [])[:6],
        "recovery_mode": False,
    }
    state["policy_decision"] = policy_decision
    state["planner_meta"] = planner_meta
    state["planner_semantic_output"] = planner_semantic_output
    if isinstance(planner_meta.get("planner_need_info_slots"), list):
        state["planner_need_info_slots"] = [str(x).strip() for x in planner_meta.get("planner_need_info_slots") if str(x).strip()]
    else:
        state["planner_need_info_slots"] = []
    state["planner_ledger_hash"] = planner_meta.get("planner_ledger_hash") or state.get("effective_ledger_hash", "")

    phase_map = planner_meta.get("phase_map_json") if isinstance(planner_meta.get("phase_map_json"), dict) else get_phase_map_v1()
    state["phase_map_json"] = phase_map

    state["progress_state"] = progress_state
    state["planner_debug"] = {
        "semantic_runtime": True,
        "planner_semantic_output": planner_semantic_output,
    }
    return state
