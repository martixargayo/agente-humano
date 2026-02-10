from negotiation.phase_migration import map_legacy_phase_to_harvard
from negotiation.phase_state_updater import postprocess_phase_candidate
from negotiation.policies import POLICIES
from negotiation.policy_planner import allowed_policy_ids
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_phase_migration_legacy_to_harvard():
    assert map_legacy_phase_to_harvard("opening") == ("climate", False)
    assert map_legacy_phase_to_harvard("discovery") == ("interests", False)
    assert map_legacy_phase_to_harvard("bargaining") == ("adjust", False)
    assert map_legacy_phase_to_harvard("closing") == ("formalize", False)
    assert map_legacy_phase_to_harvard("recovery") == ("climate", True)


def test_phase_state_updater_gates_recovery_on_off():
    progress = default_progress_state()
    prev = progress["phase_state"]
    world = default_world_state()
    world["universal_v2"] = {"clarity": {"is_vague": False}, "affect": {"confidence": 0.5}}
    world["negotiation_v2"] = {"interests": ["x"], "constraints": [], "offers": [], "agreement_state": {}}

    belief = default_belief_state()
    belief["universal"] = {
        "dynamics": {"interaction_health": "tense"},
        "behavior_guidance": {"conflict_risk": 0.7},
    }
    normalized, _meta = postprocess_phase_candidate(prev, {"phase": "interests", "confidence": 0.8}, 1, world, belief, progress)
    assert normalized["recovery_mode"] is True
    assert normalized["phase_effective"] == "climate"

    belief["universal"]["dynamics"]["interaction_health"] = "stable"
    belief["universal"]["behavior_guidance"]["conflict_risk"] = 0.1
    progress["loop_flags"] = []
    normalized2, _meta2 = postprocess_phase_candidate(normalized, {"phase": "interests", "confidence": 0.8}, 2, world, belief, progress)
    normalized3, _meta3 = postprocess_phase_candidate(normalized2, {"phase": "interests", "confidence": 0.8}, 3, world, belief, progress)
    assert normalized3["recovery_mode"] is False


def test_allowed_policy_ids_respects_phase_effective():
    progress = default_progress_state()
    progress["phase_state"].update({"phase": "formalize", "phase_effective": "formalize", "recovery_mode": False})
    world = default_world_state()
    world["negotiation"]["price_mentioned"] = True
    allowed = allowed_policy_ids(world, default_belief_state(), progress, {})
    assert "formalize_recap_confirm" in allowed
    assert "tradeoff_offer" not in allowed


def test_formalize_has_single_policy_only():
    formalize_only = [p.policy_id for p in POLICIES if p.phase_hints == ["formalize"]]
    assert formalize_only == ["formalize_recap_confirm"]
