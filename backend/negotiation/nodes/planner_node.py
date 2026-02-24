from __future__ import annotations

import time
from datetime import datetime, timezone

from ..phase_state_updater import postprocess_phase_candidate
from ..policy_planner import allowed_policy_ids, allowed_policy_ids_with_reasons, repair_policy_by_phase
from ..policies import policy_phase_catalog
from ..schemas import default_policy_decision, default_progress_state
from ..state.deps import DEFAULT_DEPS
from ..validation import normalize_policy_decision
from ..telemetry.trace_runtime import record_gate_event, record_llm_call, record_node_phase_ms


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def _clamp_step(active_plan: dict) -> tuple[dict, bool]:
    plan = dict(active_plan)
    steps = list(plan.get("steps", []))
    if not steps:
        plan["current_step_idx"] = 0
        return plan, False
    cur = int(plan.get("current_step_idx", 0) or 0)
    clamped = max(0, min(cur, len(steps) - 1))
    plan["current_step_idx"] = clamped
    return plan, clamped != cur


def _advance_step(active_plan: dict) -> tuple[dict | None, bool]:
    plan, _ = _clamp_step(active_plan)
    steps = list(plan.get("steps", []))
    if not steps:
        return None, False
    cur = int(plan.get("current_step_idx", 0) or 0)
    nxt = cur + 1
    if nxt >= len(steps):
        return None, False
    plan["current_step_idx"] = nxt
    return plan, True


def _build_active_plan_from_replan(policy_decision: dict, phase_effective: dict, turn_count: int) -> dict:
    phase_assessment = {
        "phase": phase_effective.get("phase_effective") or phase_effective.get("phase", "climate"),
        "confidence": float(phase_effective.get("confidence", 0.0) or 0.0),
        "reason": str(policy_decision.get("why_short", "") or ""),
        "evidence": [],
        "recovery_mode": bool(phase_effective.get("recovery_mode", False)),
    }
    micro_goal = str(policy_decision.get("micro_goal", "") or "Mantener avance con una acción verificable.")
    ask = [f"¿Puedes concretar: {micro_goal[:100]}?"] if micro_goal else []
    return {
        "phase_assessment": phase_assessment,
        "schema_version": "v1",
        "plan_id": f"plan_t{turn_count}",
        "created_turn": turn_count,
        "updated_turn": turn_count,
        "horizon_turns": 1,
        "current_step_idx": 0,
        "global_goal": micro_goal[:180],
        "steps": [
            {
                "step_idx": 0,
                "intent_id": "collect_new_signal",
                "micro_goal": micro_goal[:160],
                "what_to_do": f"Aplicar {policy_decision.get('policy_id', 'safe_neutral')} y pedir una señal verificable para avanzar."[:260],
                "ask": ask[:2],
                "success_criteria": ["intencion_alineada_con_info_nueva"],
                "replan_triggers": ["ambiguedad_persistente", "escalada"],
                "safe_mode": "deescalate" if bool(phase_effective.get("recovery_mode", False)) else "normal",
            }
        ],
        "required_intents": ["collect_new_signal"],
        "covered_intents": ["collect_new_signal"],
        "plan_constraints": {
            "max_questions_per_turn": 2,
            "must_avoid": ["escalar_tension"],
            "stop_conditions": ["amenaza"],
        },
    }




def _normalize_intent_id(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    out = []
    prev_us = False
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
            prev_us = True
    return "".join(out).strip("_")[:64]


def validate_active_plan_against_ledger(active_plan: dict | None, plan_ledger: dict | None) -> tuple[bool, list[str]]:
    if not isinstance(active_plan, dict):
        return False, ["plan_not_dict"]
    steps = active_plan.get("steps") if isinstance(active_plan.get("steps"), list) else []
    if not steps:
        return False, ["steps_missing"]

    resolved = set()
    for item in (plan_ledger or {}).get("resolved_intents", []) if isinstance((plan_ledger or {}).get("resolved_intents"), list) else []:
        if not isinstance(item, dict):
            continue
        rid = _normalize_intent_id(item.get("intent_id"))
        if rid:
            resolved.add(rid)

    seen: set[str] = set()
    errors: list[str] = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"step_{idx}_not_dict")
            continue
        intent_id = _normalize_intent_id(step.get("intent_id"))
        if not intent_id:
            errors.append(f"step_{idx}_intent_id_missing")
            continue
        if intent_id in seen:
            errors.append(f"duplicate_intent_id:{intent_id}")
        seen.add(intent_id)
        if intent_id in resolved:
            errors.append(f"intent_already_resolved:{intent_id}")
    return len(errors) == 0, errors


def _build_executor_instruction(active_plan: dict | None) -> dict:
    if not isinstance(active_plan, dict):
        return {}
    steps = list(active_plan.get("steps", []))
    if not steps:
        return {}
    cur = int(active_plan.get("current_step_idx", 0) or 0)
    cur = max(0, min(cur, len(steps) - 1))
    step = steps[cur] if isinstance(steps[cur], dict) else {}
    constraints = active_plan.get("plan_constraints") or {}
    return {
        "schema_version": "v1",
        "plan_id": str(active_plan.get("plan_id", ""))[:40],
        "step_idx": cur,
        "step_micro_goal": str(step.get("micro_goal", ""))[:160],
        "instruction": str(step.get("what_to_do", ""))[:320],
        "ask": list(step.get("ask", []))[:2],
        "safe_mode": str(step.get("safe_mode", "normal") or "normal"),
        "must_avoid": list(constraints.get("must_avoid", []))[:4],
        "stop_conditions": list(constraints.get("stop_conditions", []))[:4],
        "max_questions_per_turn": int(constraints.get("max_questions_per_turn", 2) or 2),
        "trace_tags": ["plan_instruction"],
    }


def phase_policy_planner_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    progress_state = state.get("progress_state", {})
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    turn_count = state.get("turn_count", 0) or 0
    policy_state = progress_state.get("policy_state", {})
    planner_request = str(policy_state.get("planner_request", "replan_policy") or "replan_policy")
    advance_step = bool(progress_state.get("advance_step", False))
    policy_plan_judgement = state.get("policy_plan_judgement") if isinstance(state.get("policy_plan_judgement"), dict) else {}
    judgement_skip_planner = bool(policy_plan_judgement.get("skip_planner", False))
    previous_plan = progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None

    allowed_all, filtered_reasons = allowed_policy_ids_with_reasons(
        state["world_state"],
        state["belief_state"],
        progress_state,
        state.get("hard_constraints_struct"),
    )
    plan_id_before = str((previous_plan or {}).get("plan_id", ""))
    step_idx_before = int((previous_plan or {}).get("current_step_idx", 0) or 0)

    planner_skipped = False
    skip_reason = ""
    planner_meta: dict = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "planner_skipped": False,
        "planner_skip_reason": "",
        "planner_request": planner_request,
        "advance_step": advance_step,
        "judgement_skip_planner": judgement_skip_planner,
        "allowed_policy_ids": allowed_all,
    }
    planner_debug = {
        "inputs": {
            "planner_request": planner_request,
            "advance_step": advance_step,
            "judgement_skip_planner": judgement_skip_planner,
            "active_plan_status": str(progress_state.get("active_plan_status", "none") or "none"),
            "active_plan_plan_id": plan_id_before,
            "active_plan_current_step_idx": step_idx_before,
            "policy_plan_judgement_plan_status": str((state.get("policy_plan_judgement") or {}).get("plan_status", "")),
            "policy_plan_judgement_degraded": bool((state.get("policy_plan_judgement") or {}).get("degraded", False)),
        },
        "gate_decision": {"gate_path": "", "gate_reason_codes": []},
        "plan_handling": {},
        "policy_selection": {
            "allowed_policy_ids_count": len(allowed_all),
            "filter_reasons": filtered_reasons,
            "policy_pre_repair": None,
            "policy_post_repair": None,
            "repair_meta": {},
        },
        "llm_call": {
            "planner_llm_called": False,
            "planner_latency_ms": 0,
            "planner_failed": False,
            "planner_fallback_used": False,
            "planner_error_stage": "",
            "normalization_issues": [],
        },
        "executor_instruction_contract": {},
    }

    phase_candidate = None
    phase_effective = progress_state.get("phase_state") or default_progress_state()["phase_state"]
    policy_decision = default_policy_decision()
    active_plan_status = "none"
    active_plan = previous_plan

    if planner_request == "continue_policy" and previous_plan:
        if advance_step:
            steps = list(previous_plan.get("steps", [])) if isinstance(previous_plan, dict) else []
            cur_idx = int(previous_plan.get("current_step_idx", 0) or 0) if isinstance(previous_plan, dict) else 0
            last_idx = len(steps) - 1
            if steps and cur_idx >= last_idx:
                planner_request = "replan_policy"
                planner_meta["advance_step_reached_last_step"] = True
                planner_debug["gate_decision"]["gate_path"] = "replan_last_step_completed"
                planner_debug["gate_decision"]["gate_reason_codes"] = ["advance_step_last_step"]
            else:
                advanced_plan, did_advance = _advance_step(previous_plan)
                if did_advance and advanced_plan:
                    active_plan = advanced_plan
                    active_plan["updated_turn"] = turn_count
                    active_plan_status = "active"
                    planner_skipped = True
                    skip_reason = "advance_step_without_planner"
                    planner_debug["gate_decision"]["gate_path"] = "advance_step_no_llm"
                    planner_debug["gate_decision"]["gate_reason_codes"] = ["advance_step_true"]
                else:
                    planner_request = "replan_policy"
                    planner_meta["advance_step_out_of_range"] = True
                    planner_debug["gate_decision"]["gate_path"] = "replan_out_of_range"
                    planner_debug["gate_decision"]["gate_reason_codes"] = ["step_out_of_range"]
        elif judgement_skip_planner:
            active_plan, _ = _clamp_step(previous_plan)
            active_plan["updated_turn"] = turn_count
            active_plan_status = "active"
            planner_skipped = True
            skip_reason = "judge_skip_planner"
            planner_debug["gate_decision"]["gate_path"] = "skip_judge_flag"
            planner_debug["gate_decision"]["gate_reason_codes"] = ["judge_skip_planner_true"]
        else:
            active_plan, _ = _clamp_step(previous_plan)
            active_plan["updated_turn"] = turn_count
            active_plan_status = "active"
            reusable_policy_id = str(
                policy_state.get("policy_id")
                or progress_state.get("last_chosen_policy_id")
                or progress_state.get("last_executed_policy_id")
                or ""
            )
            if reusable_policy_id and reusable_policy_id in allowed_all:
                policy_decision = default_policy_decision()
                policy_decision["policy_id"] = reusable_policy_id
                policy_decision["reason"] = "Se mantiene la policy activa sin replan."
                policy_decision["why_short"] = "continue_same_step"
                planner_skipped = True
                skip_reason = "continue_same_step_without_planner"
                planner_debug["gate_decision"]["gate_path"] = "continue_same_step_no_llm"
                planner_debug["gate_decision"]["gate_reason_codes"] = ["continue_policy_reuse"]
            else:
                planner_request = "replan_policy"
                planner_meta["continue_policy_missing_reusable_policy"] = True
                planner_debug["gate_decision"]["gate_path"] = "replan_missing_policy"
                planner_debug["gate_decision"]["gate_reason_codes"] = ["missing_reusable_policy"]

    gate_reason_codes = list((planner_debug.get("gate_decision") or {}).get("gate_reason_codes", []))
    gate_reason = skip_reason or str((planner_debug.get("gate_decision") or {}).get("gate_path", ""))
    gate_started = time.perf_counter()
    gate_started_ts = datetime.now(timezone.utc).isoformat()
    record_gate_event(
        state,
        name="planner_gate",
        node="phase_policy_planner",
        decision="skipped" if planner_skipped else "executed",
        reason=gate_reason,
        reason_codes=gate_reason_codes,
        gate_inputs={
            "planner_request": planner_request,
            "active_plan_present": bool(previous_plan),
            "advance_step": advance_step,
            "judgement_skip_planner": judgement_skip_planner,
            "reusable_policy_id": str((policy_state or {}).get("policy_id", "")),
            "allowed_policy_ids_count": len(allowed_all),
        },
        gate_rule_id="planner_skip_gate",
        gate_version="v1",
        started=gate_started,
        started_ts=gate_started_ts,
    )

    if not planner_skipped:
        planner_call_meta: dict = {}
        started = time.perf_counter()
        try:
            phase_candidate, policy_decision, planner_call_meta = deps.plan_phase_policy(
                world_state=state["world_state"],
                world_diff=state.get("world_diff", {}),
                belief_state=state["belief_state"],
                progress_state=progress_state,
                policy_state=policy_state,
                policy_plan_summary=state.get("policy_plan_summary"),
                objective=state["objective"],
                constraints=state.get("constraints", ""),
                constraints_struct=state.get("hard_constraints_struct", {}),
                recent_context=state.get("recent_history_text", ""),
                allowed_policy_ids=allowed_all,
                advisor_recs=state.get("advisor_recs") if isinstance(state.get("advisor_recs"), dict) else {},
                judge_result=state.get("policy_plan_judgement") if isinstance(state.get("policy_plan_judgement"), dict) else {},
                memory_short=str(state.get("short_memory", "") or ""),
                memory_long=str(state.get("long_memory", "") or ""),
            )
            planner_meta.update(planner_call_meta)
            planner_debug["llm_call"]["planner_llm_called"] = True
        except Exception as exc:
            planner_meta["planner_failed"] = True
            planner_meta["planner_fallback_used"] = True
            planner_meta["planner_error"] = str(exc)
            policy_decision = default_policy_decision()
            phase_candidate = {
                "phase": "climate",
                "confidence": 0.0,
                "reasons": [],
                "signals": [],
                "alternatives": [],
            }
        planner_debug["llm_call"]["planner_latency_ms"] = int((time.perf_counter() - started) * 1000)
        planner_debug["llm_call"]["planner_failed"] = bool(planner_meta.get("planner_failed", False))
        planner_debug["llm_call"]["planner_fallback_used"] = bool(planner_meta.get("planner_fallback_used", False))
        planner_debug["llm_call"]["planner_error_stage"] = str(planner_meta.get("planner_error_stage", ""))
        planner_debug["llm_call"]["normalization_issues"] = list(planner_meta.get("issues", []))[:12]
        record_llm_call(
            state,
            name="planner_llm",
            node="phase_policy_planner",
            started=started,
            ok=not bool(planner_meta.get("planner_failed", False)),
            model=planner_meta.get("planner_model"),
            tokens_in=planner_meta.get("planner_tokens_in"),
            tokens_out=planner_meta.get("planner_tokens_out"),
            retry_count=1 if bool(planner_meta.get("planner_fallback_used", False)) else 0,
            error_stage=str(planner_meta.get("planner_error_stage", "")),
            error=str(planner_meta.get("planner_error", "")),
            input_prompt_rendered=str(planner_meta.get("planner_input_prompt_rendered", "")),
            output_text_rendered=str(planner_meta.get("planner_output_text_rendered", "")),
            input_payload_raw=planner_meta.get("planner_input_payload_raw"),
            output_payload_raw=planner_meta.get("planner_output_payload_raw"),
        )

        if not planner_debug["gate_decision"]["gate_path"]:
            planner_debug["gate_decision"]["gate_path"] = "replan_call_llm"
            planner_debug["gate_decision"]["gate_reason_codes"] = ["request_replan"]

        phase_effective, phase_meta = postprocess_phase_candidate(
            prev_phase_state=progress_state.get("phase_state"),
            phase_candidate=phase_candidate,
            turn_count=turn_count,
            world_state=state.get("world_state", {}),
            belief_state=state.get("belief_state", {}),
            progress_state=progress_state,
        )
        phase_effective["last_updated_turn"] = turn_count
        state["phase_meta"] = phase_meta
        normalized_policy, issues = normalize_policy_decision(policy_decision, allowed_all)
        if issues:
            planner_meta["policy_normalization_changed"] = True
            planner_meta["issues"] = issues
        policy_decision = normalized_policy
        active_plan_from_llm = planner_call_meta.get("active_plan") if isinstance(planner_call_meta.get("active_plan"), dict) else None
        active_plan = active_plan_from_llm or _build_active_plan_from_replan(policy_decision, phase_effective, turn_count)
        plan_ledger = progress_state.get("plan_ledger") if isinstance(progress_state.get("plan_ledger"), dict) else {}
        plan_valid, plan_errors = validate_active_plan_against_ledger(active_plan, plan_ledger)
        if not plan_valid:
            planner_meta["planner_failed"] = True
            planner_meta["planner_fallback_used"] = True
            planner_meta["planner_error"] = "invalid_plan_against_ledger"
            planner_meta["plan_validation_errors"] = plan_errors
            planner_debug["gate_decision"]["gate_reason_codes"] = list(planner_debug["gate_decision"].get("gate_reason_codes", [])) + ["invalid_plan_against_ledger"]
            active_plan = _build_active_plan_from_replan(policy_decision, phase_effective, turn_count)
            fallback_valid, fallback_errors = validate_active_plan_against_ledger(active_plan, plan_ledger)
            planner_meta["fallback_plan_valid"] = fallback_valid
            if not fallback_valid:
                planner_meta["planner_error"] = "invalid_fallback_plan_against_ledger"
                planner_meta["plan_validation_errors"] = plan_errors + fallback_errors
        active_plan_status = "active"

    planner_meta["planner_request"] = planner_request
    planner_meta["planner_skipped"] = planner_skipped
    planner_meta["planner_skip_reason"] = skip_reason

    progress_state["phase_state"] = phase_effective
    progress_state["active_plan_status"] = active_plan_status if active_plan else "none"
    progress_state["active_plan"] = active_plan
    progress_state["advance_step"] = False

    if planner_skipped:
        gate_state["planner_skip_count"] = int(gate_state.get("planner_skip_count", 0) or 0) + 1
    else:
        gate_state["last_planner_refresh_turn"] = turn_count
    progress_state["gate_state"] = gate_state

    state["allowed_policy_ids"] = allowed_all
    state["phase_candidate"] = phase_candidate
    state["phase_effective"] = phase_effective
    state["policy_pre_repair"] = None
    state["policy_post_repair"] = policy_decision
    state["policy_decision"] = policy_decision
    state["planner_meta"] = planner_meta
    if isinstance(planner_meta.get("executor_instruction"), dict) and planner_meta.get("planner_version") == "v2":
        state["executor_instruction"] = planner_meta.get("executor_instruction")
    else:
        state["executor_instruction"] = _build_executor_instruction(active_plan)
    plan_id_after = str((active_plan or {}).get("plan_id", ""))
    step_idx_after = int((active_plan or {}).get("current_step_idx", 0) or 0)
    planner_debug["plan_handling"] = {
        "plan_reused": bool(plan_id_before and plan_id_before == plan_id_after),
        "plan_id_before": plan_id_before,
        "plan_id_after": plan_id_after,
        "step_idx_before": step_idx_before,
        "step_idx_after": step_idx_after,
        "executor_instruction_derived_from_step_idx": int((state.get("executor_instruction") or {}).get("step_idx", 0) or 0),
    }
    planner_debug["policy_selection"]["policy_post_repair"] = state.get("policy_post_repair")
    planner_debug["executor_instruction_contract"] = {
        "plan_id": str((state.get("executor_instruction") or {}).get("plan_id", "")),
        "step_idx": int((state.get("executor_instruction") or {}).get("step_idx", 0) or 0),
        "safe_mode": str((state.get("executor_instruction") or {}).get("safe_mode", "normal")),
        "must_avoid": list((state.get("executor_instruction") or {}).get("must_avoid", []))[:4],
        "max_questions_per_turn": int((state.get("executor_instruction") or {}).get("max_questions_per_turn", 2) or 2),
        "stop_conditions": list((state.get("executor_instruction") or {}).get("stop_conditions", []))[:4],
    }
    planner_debug_v2 = {
        "input_compact": {
            "phase_effective": state.get("phase_effective") or {},
            "allowed_policy_ids": allowed_all[:12],
            "planner_request": planner_request,
            "gate_decisions_influential": planner_debug.get("gate_decision", {}),
        },
        "output": {
            "selected_policy": (state.get("policy_decision") or {}).get("policy_id", ""),
            "policy_ranking_top5": list((phase_candidate or {}).get("alternatives", []))[:5],
            "normalization": {
                "changed": bool(planner_meta.get("policy_normalization_changed", False)),
                "issues": list(planner_meta.get("issues", []))[:8],
            },
            "fallback": {
                "used": bool(planner_meta.get("planner_fallback_used", False)),
                "reason": str(planner_meta.get("planner_error", ""))[:140],
            },
        },
        "reasoning_trace": {
            "selected_policy": (state.get("policy_decision") or {}).get("policy_id", ""),
            "why_short": str((state.get("policy_decision") or {}).get("why_short", ""))[:140],
            "key_factors": list((phase_candidate or {}).get("reasons", []))[:6],
            "rejected_alternatives": [
                {"policy": str(item.get("policy_id", "")), "reason_short": str(item.get("reason", ""))[:100]}
                for item in list((phase_candidate or {}).get("alternatives", []))[:4]
                if isinstance(item, dict)
            ],
        },
    }
    state["planner_debug"] = planner_debug
    state["planner_debug_v2"] = planner_debug_v2
    state["progress_state"] = progress_state
    state["gate_meta"] = {
        "world_skipped": state.get("extractor_meta", {}).get("extractor_skipped", False),
        "belief_skipped": state.get("belief_update_meta", {}).get("belief_update_skipped", False),
        "planner_skipped": planner_skipped,
        "skip_reasons": {
            "world": state.get("extractor_meta", {}).get("skip_reason", ""),
            "belief": state.get("belief_update_meta", {}).get("skip_reason", ""),
            "planner": skip_reason,
        },
    }
    return state
