from __future__ import annotations

from ..phase_state_updater import postprocess_phase_candidate
from ..policy_planner import allowed_policy_ids
from ..schemas import default_policy_decision, default_progress_state
from ..state.deps import DEFAULT_DEPS
from ..validation import normalize_policy_decision


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
                "micro_goal": micro_goal[:160],
                "what_to_do": f"Aplicar {policy_decision.get('policy_id', 'safe_neutral')} y pedir una señal verificable para avanzar."[:260],
                "ask": ask[:2],
                "success_criteria": ["nueva_informacion_verificable"],
                "replan_triggers": ["ambiguedad_persistente", "escalada"],
                "safe_mode": "deescalate" if bool(phase_effective.get("recovery_mode", False)) else "normal",
            }
        ],
        "plan_constraints": {
            "max_questions_per_turn": 2,
            "must_avoid": ["escalar_tension"],
            "stop_conditions": ["amenaza"],
        },
    }


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
    previous_plan = progress_state.get("active_plan") if isinstance(progress_state.get("active_plan"), dict) else None

    allowed_all = allowed_policy_ids(
        state["world_state"],
        state["belief_state"],
        progress_state,
        state.get("hard_constraints_struct"),
    )

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
    }

    phase_candidate = None
    phase_effective = progress_state.get("phase_state") or default_progress_state()["phase_state"]
    policy_decision = default_policy_decision()
    active_plan_status = "none"
    active_plan = previous_plan

    if planner_request == "continue_policy" and previous_plan:
        if advance_step:
            advanced_plan, did_advance = _advance_step(previous_plan)
            if did_advance and advanced_plan:
                active_plan = advanced_plan
                active_plan["updated_turn"] = turn_count
                active_plan_status = "active"
                planner_skipped = True
                skip_reason = "advance_step_without_planner"
            else:
                planner_request = "replan_policy"
                planner_meta["advance_step_out_of_range"] = True
        else:
            active_plan, _ = _clamp_step(previous_plan)
            active_plan["updated_turn"] = turn_count
            active_plan_status = "active"
            planner_skipped = True
            skip_reason = "continue_policy"

    if planner_request != "continue_policy" or not active_plan:
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
            )
            planner_meta.update(planner_call_meta)
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
        active_plan = _build_active_plan_from_replan(policy_decision, phase_effective, turn_count)
        active_plan_status = "active"

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
    state["executor_instruction"] = _build_executor_instruction(active_plan)
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
