from __future__ import annotations

from ..phase_state_updater import postprocess_phase_candidate
from ..policies import get_policy, policy_phase_catalog, safe_neutral_policy_id
from ..policy_planner import (
    allowed_policy_ids,
    allowed_policy_ids_no_phase,
    repair_policy_by_phase,
)
from ..schemas import default_policy_decision, default_policy_state, default_progress_state
from ..state.deps import DEFAULT_DEPS
from ..validation import normalize_policy_decision


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def _current_step_for_policy(policy_id: str, step_idx: int):
    policy = get_policy(policy_id)
    plan = policy.plan if policy else None
    if not plan or step_idx < 0 or step_idx >= len(plan.steps):
        return None
    return plan.steps[step_idx]


def phase_policy_planner_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    progress_state = state.get("progress_state", {})
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    turn_count = state.get("turn_count", 0) or 0

    allowed_all = allowed_policy_ids(
        state["world_state"],
        state["belief_state"],
        progress_state,
        state.get("hard_constraints_struct"),
    )

    phase_candidate = None
    phase_effective = progress_state.get("phase_state")
    policy_pre_repair = None
    policy_post_repair = None
    policy_decision = default_policy_decision()
    planner_skipped = False
    skip_reason = ""

    planner_meta: dict = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "planner_skipped": planner_skipped,
        "planner_skip_reason": skip_reason,
        "allowed_policy_ids": allowed_all,
        "allowed_policy_ids_all_count": len(allowed_all),
        "policy_allowed_validation_basis": "allowed_all_no_phase",
        "policy_id_llm": "",
        "policy_id_final": "",
        "policy_phase_mismatch": False,
        "phase_policy_repair_used": False,
        "phase_policy_repair_reason": "",
    }

    policy_state = progress_state.get("policy_state", default_policy_state())
    current_step = _current_step_for_policy(
        policy_state.get("policy_id", ""), int(policy_state.get("step_idx", 0))
    )
    if policy_state.get("planner_request") == "continue_policy" and current_step:
        planner_skipped = True
        skip_reason = "continue_policy"
        policy_decision = {
            "policy_id": policy_state.get("policy_id", ""),
            "reason": "Continuar policy multi-turn sin planner.",
            "micro_goal": current_step.micro_goal,
            "risk_posture": "low",
            "why_short": "",
            "inputs_used": [],
        }
        planner_meta["planner_skipped"] = planner_skipped
        planner_meta["planner_skip_reason"] = skip_reason
    else:
        planner_skipped = False
        skip_reason = ""
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
            policy_decision = {
                "policy_id": safe_neutral_policy_id(),
                "reason": "Fallback seguro por error de planner.",
                "micro_goal": "Mantener conversación abierta con una pregunta breve.",
                "risk_posture": "low",
                "why_short": "",
                "inputs_used": [],
            }
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
        policy_pre_repair = dict(policy_decision)
        policy_id_llm = policy_decision.get("policy_id", "")
        effective_phase = phase_effective.get("phase_effective") or phase_effective.get("phase", "climate")
        phase_catalog = policy_phase_catalog()
        policy_phase_mismatch = effective_phase not in phase_catalog.get(policy_id_llm, [])
        planner_meta["policy_phase_mismatch"] = policy_phase_mismatch
        planner_meta["policy_id_llm"] = policy_id_llm

        if policy_phase_mismatch:
            phase_supported = [
                policy_id
                for policy_id in allowed_all
                if effective_phase in phase_catalog.get(policy_id, [])
            ]
            if phase_supported:
                repaired_id, repair_meta = repair_policy_by_phase(
                    policy_id_llm,
                    phase_supported,
                    phase_catalog,
                    effective_phase,
                    None,
                    None,
                    policy_attempts=progress_state.get("policy_attempts", {}),
                )
                if repaired_id and repaired_id != policy_decision.get("policy_id"):
                    policy_decision["policy_id"] = repaired_id
                planner_meta.update(repair_meta)
            else:
                fallback_id = safe_neutral_policy_id()
                if fallback_id not in allowed_all and allowed_all:
                    fallback_id = allowed_all[0]
                policy_decision["policy_id"] = fallback_id
                planner_meta.update(
                    {
                        "phase_repair_used": True,
                        "phase_repair_from": policy_id_llm,
                        "phase_repair_to": fallback_id,
                        "phase_repair_mode": "fallback_no_phase_match",
                        "phase_repair_attempts_blocked": [],
                    }
                )

        normalized_policy, issues = normalize_policy_decision(policy_decision, allowed_all)
        if issues:
            planner_meta["policy_normalization_changed"] = True
            planner_meta["issues"] = planner_meta.get("issues", []) + issues
        policy_decision = normalized_policy
        policy_post_repair = dict(policy_decision)
        planner_meta["phase_policy_repair_used"] = planner_meta.get("phase_repair_used", False)
        planner_meta["phase_policy_repair_reason"] = planner_meta.get("phase_repair_mode", "")
        planner_meta["policy_id_final"] = policy_decision.get("policy_id", "")
        state["phase_meta"] = phase_meta

    if not phase_effective:
        phase_effective = progress_state.get("phase_state") or default_progress_state()["phase_state"]
    progress_state["phase_state"] = phase_effective

    if planner_skipped:
        gate_state["planner_skip_count"] = int(gate_state.get("planner_skip_count", 0) or 0) + 1
    else:
        gate_state["last_planner_refresh_turn"] = turn_count
    progress_state["gate_state"] = gate_state

    if not state.get("phase_meta"):
        state["phase_meta"] = {
            "phase_update_used": False,
            "phase_update_reason": "policy_continue" if planner_skipped else "planner",
        }
    planner_meta["phase_meta"] = state.get("phase_meta", {})
    planner_meta["phase_state"] = progress_state.get("phase_state", {})
    planner_meta["phase_candidate"] = phase_candidate
    planner_meta["phase_effective"] = phase_effective
    planner_meta["policy_id_final"] = policy_decision.get("policy_id", "")

    state["phase_candidate"] = phase_candidate
    state["phase_effective"] = phase_effective
    state["policy_pre_repair"] = policy_pre_repair
    state["policy_post_repair"] = policy_post_repair or policy_decision
    state["policy_decision"] = policy_decision
    state["planner_meta"] = planner_meta
    state["allowed_policy_ids"] = allowed_all
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
        "skip_counters": {
            "world": gate_state.get("world_skip_count", 0),
            "belief": gate_state.get("belief_skip_count", 0),
            "planner": gate_state.get("planner_skip_count", 0),
        },
        "last_refresh_turn": {
            "world": gate_state.get("last_world_refresh_turn", 0),
            "belief": gate_state.get("last_belief_refresh_turn", 0),
            "planner": gate_state.get("last_planner_refresh_turn", 0),
        },
        "world_gate_features": state.get("extractor_meta", {}).get("world_gate_features", {}),
    }
    return state
