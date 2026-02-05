from __future__ import annotations

import os

from ..gate_utils import (
    gate_phase_policy,
    loop_flags_changed,
    precedence_signature,
    select_policy_id_on_skip,
    stable_allowed_ids_hash,
)
from ..phase_state_updater import postprocess_phase_candidate
from ..policies import policy_phase_catalog, safe_neutral_policy_id
from ..policy_planner import (
    _required_inputs_met,
    _violates_hard_constraints,
    allowed_policy_ids,
    apply_intent_constraints,
    apply_precedence_constraints,
    repair_policy_by_phase,
)
from ..schemas import default_policy_decision, default_progress_state
from ..state.deps import DEFAULT_DEPS
from ..validation import normalize_policy_decision


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def phase_policy_planner_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    progress_state = state.get("progress_state", {})
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    turn_count = state.get("turn_count", 0) or 0

    allowed_base = allowed_policy_ids(
        state["world_state"], state["belief_state"], state["progress_state"]
    )
    allowed_prec, prec_meta = apply_precedence_constraints(allowed_base, state.get("precedence"))
    allowed_final, preferred, intent_meta = apply_intent_constraints(
        allowed_prec, state.get("intent_hint")
    )
    required_filtered = [
        pid for pid in allowed_final if _required_inputs_met(pid, state["world_state"])
    ]
    if required_filtered:
        allowed_final = required_filtered
    allowed_final = [
        pid
        for pid in allowed_final
        if not _violates_hard_constraints(
            pid, state["world_state"], state.get("constraints_struct")
        )
    ]
    if not allowed_final:
        allowed_final = [safe_neutral_policy_id()]

    allowed_hash = stable_allowed_ids_hash(allowed_final)
    prev_allowed_hash = gate_state.get("allowed_ids_hash_prev", "")
    allowed_hash_changed = allowed_hash != prev_allowed_hash
    stable_count = int(gate_state.get("allowed_ids_hash_stable_count", 0) or 0)
    stable_count = stable_count + 1 if allowed_hash == prev_allowed_hash else 0

    current_signature = state.get("precedence_signature", "")
    prev_signature = gate_state.get("precedence_signature_prev", "")
    precedence_changed = current_signature != prev_signature
    loop_flags_prev = gate_state.get("loop_flags_prev", [])
    loop_flags_current = progress_state.get("loop_flags", [])
    loop_flags_changed_flag = loop_flags_changed(loop_flags_prev, loop_flags_current)
    intent_transition = (state.get("intent_meta") or {}).get("intent_transition")
    intent_transition_present = bool(intent_transition and intent_transition != "none")

    planner_skipped, skip_reason, planner_gate_meta = gate_phase_policy(
        world_diff=state.get("world_diff", {}),
        precedence_changed=precedence_changed,
        intent_transition_present=intent_transition_present,
        loop_flags_changed_flag=loop_flags_changed_flag,
        allowed_ids_hash_changed=allowed_hash_changed,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_planner_refresh_turn", 0) or 0),
        interval=int(os.getenv("PHASE_POLICY_REFRESH_INTERVAL_TURNS", "2")),
    )

    phase_candidate = None
    phase_effective = progress_state.get("phase_state")
    policy_pre_repair = None
    policy_post_repair = None
    policy_decision = default_policy_decision()
    planner_meta: dict = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "planner_skipped": planner_skipped,
        "planner_skip_reason": skip_reason,
        "allowed_policy_ids": allowed_final,
        "allowed_policy_ids_base": allowed_base,
        "allowed_policy_ids_after_precedence": allowed_prec,
        "allowed_policy_ids_after_intent": allowed_final,
        "allowed_policy_ids_after_required_inputs": required_filtered,
        "intent_preferred_policy_ids": preferred,
        "allowed_ids_hash": allowed_hash,
        "allowed_ids_hash_prev": prev_allowed_hash,
        "allowed_ids_hash_stable_count": stable_count,
        "planner_gate_features": planner_gate_meta,
    }
    planner_meta.update(prec_meta)
    planner_meta.update(intent_meta)

    if planner_skipped:
        chosen_id, skip_mode = select_policy_id_on_skip(
            last_policy_chosen=progress_state.get("last_chosen_policy_id", ""),
            allowed_policy_ids=allowed_final,
            policy_attempts=progress_state.get("policy_attempts", {}),
            loop_flags=loop_flags_current,
            safe_neutral_policy_id=safe_neutral_policy_id(),
            max_attempts=int(os.getenv("PLANNER_SKIP_MAX_ATTEMPTS", "3")),
        )
        policy_decision = {
            "policy_id": chosen_id,
            "reason": "Planner skipped; fallback policy selected.",
            "micro_goal": "Mantener conversación abierta con una pregunta breve.",
            "risk_posture": "low",
            "why_short": "",
            "inputs_used": [],
        }
        planner_meta["planner_skip_mode"] = skip_mode
    else:
        phase_candidate, policy_decision, planner_call_meta = deps.plan_phase_policy(
            world_state=state["world_state"],
            world_diff=state.get("world_diff", {}),
            belief_state=state["belief_state"],
            progress_state=progress_state,
            intent_hint=state.get("intent_hint"),
            precedence=state.get("precedence"),
            objective=state["objective"],
            constraints=state.get("constraints", ""),
            constraints_struct=state.get("constraints_struct", {}),
            recent_context=state.get("recent_history_text", ""),
            allowed_policy_ids=allowed_final,
        )
        planner_meta.update(planner_call_meta)
        phase_effective, phase_meta = postprocess_phase_candidate(
            prev_phase_state=progress_state.get("phase_state"),
            phase_candidate=phase_candidate,
            turn_count=turn_count,
            precedence=state.get("precedence"),
        )
        phase_effective["last_updated_turn"] = turn_count
        policy_pre_repair = dict(policy_decision)
        commitment = (state.get("intent_hint") or {}).get("commitment_level")
        repaired_id, repair_meta = repair_policy_by_phase(
            policy_decision.get("policy_id", ""),
            allowed_final,
            policy_phase_catalog(),
            phase_effective.get("phase", "opening"),
            preferred,
            commitment,
            policy_attempts=progress_state.get("policy_attempts", {}),
        )
        if repaired_id and repaired_id != policy_decision.get("policy_id"):
            policy_decision["policy_id"] = repaired_id
        planner_meta.update(repair_meta)
        normalized_policy, issues = normalize_policy_decision(policy_decision, allowed_final)
        if issues:
            planner_meta["policy_normalization_changed"] = True
            planner_meta["issues"] = planner_meta.get("issues", []) + issues
        policy_decision = normalized_policy
        policy_post_repair = dict(policy_decision)
        state["phase_meta"] = phase_meta

    if not phase_effective:
        phase_effective = progress_state.get("phase_state") or default_progress_state()["phase_state"]
    progress_state["phase_state"] = phase_effective

    if planner_skipped:
        gate_state["planner_skip_count"] = int(gate_state.get("planner_skip_count", 0) or 0) + 1
    else:
        gate_state["last_planner_refresh_turn"] = turn_count
    gate_state["allowed_ids_hash_prev"] = allowed_hash
    gate_state["allowed_ids_hash_stable_count"] = stable_count
    gate_state["precedence_signature_prev"] = current_signature
    gate_state["loop_flags_prev"] = list(loop_flags_current)
    progress_state["gate_state"] = gate_state

    if not state.get("phase_meta"):
        state["phase_meta"] = {
            "phase_update_used": False,
            "phase_update_reason": "planner_skip" if planner_skipped else "planner",
        }
    planner_meta["intent_meta"] = state.get("intent_meta", {})
    planner_meta["phase_meta"] = state.get("phase_meta", {})
    planner_meta["phase_state"] = progress_state.get("phase_state", {})

    state["phase_candidate"] = phase_candidate
    state["phase_effective"] = phase_effective
    state["policy_pre_repair"] = policy_pre_repair
    state["policy_post_repair"] = policy_post_repair or policy_decision
    state["policy_decision"] = policy_decision
    state["planner_meta"] = planner_meta
    state["allowed_policy_ids"] = allowed_final
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
        "planner_gate_features": planner_gate_meta,
        "allowed_ids_hash": allowed_hash,
        "allowed_ids_hash_prev": prev_allowed_hash,
        "allowed_ids_hash_stable_count": stable_count,
    }
    return state
