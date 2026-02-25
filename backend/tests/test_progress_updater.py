from negotiation.progress_updater import _has_info_delta


def test_has_info_delta_handles_split_world_diff():
    world_diff = {
        "domain": {"price_mentioned": {"before": False, "after": True}},
        "interaction": {"implicit_acceptance": {"before": False, "after": True}},
    }
    assert _has_info_delta(world_diff) is True


def test_has_info_delta_handles_legacy_world_diff():
    world_diff = {"price_mentioned": {"before": False, "after": True}}
    assert _has_info_delta(world_diff) is True


def test_has_info_delta_ignores_interaction_only():
    world_diff = {"interaction": {"implicit_acceptance": {"before": False, "after": True}}}
    assert _has_info_delta(world_diff) is False


from negotiation.progress_updater import update_progress_state
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state, default_world_state


def _judgement(status: str, *, plan_id: str = "p1", step_idx: int = 0):
    return {
        "plan_presence": "active",
        "plan_status": status,
        "plan_id": plan_id,
        "evaluated_step_idx": step_idx,
        "evidence": [{"quote": "ok", "source": "user_message"}],
    }


def _plan(plan_id: str = "p1", step_idx: int = 0):
    return {"plan_id": plan_id, "current_step_idx": step_idx, "steps": [{"intent_id": "a"}, {"intent_id": "b"}]}


def test_same_step_counter_increments_and_resets_with_plan_and_step():
    prev = default_progress_state()

    p1 = update_progress_state(
        prev_progress=prev,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        policy_plan_judgement=_judgement("continue_same_step", plan_id="p1", step_idx=0),
        active_plan=_plan("p1", 0),
    )
    assert p1["same_step_no_progress_turns"] == 1

    p2 = update_progress_state(
        prev_progress=p1,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        policy_plan_judgement=_judgement("continue_same_step", plan_id="p1", step_idx=0),
        active_plan=_plan("p1", 0),
    )
    assert p2["same_step_no_progress_turns"] == 2
    assert p2["no_progress_same_step_turns"] == 2

    p3 = update_progress_state(
        prev_progress=p2,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        policy_plan_judgement=_judgement("continue_same_step", plan_id="p1", step_idx=1),
        active_plan=_plan("p1", 1),
    )
    assert p3["same_step_no_progress_turns"] == 0

    p4 = update_progress_state(
        prev_progress=p3,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        policy_plan_judgement=_judgement("interrupted_replan", plan_id="p2", step_idx=0),
        active_plan=_plan("p2", 0),
    )
    assert p4["same_step_no_progress_turns"] == 0


def test_blocked_topics_ttl_decays_and_applies_advisor_signals():
    prev = default_progress_state()
    prev["plan_ledger"]["blocked_topics"] = {"documentacion": 2}

    out = update_progress_state(
        prev_progress=prev,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        policy_plan_judgement=_judgement("continue_same_step"),
        active_plan=_plan(),
        advisor_signals={"force_replan": True, "blocked_topics": ["mantenimiento"], "block_ttl_turns": 2},
    )
    assert out["plan_ledger"]["blocked_topics"]["documentacion"] == 1
    assert out["plan_ledger"]["blocked_topics"]["mantenimiento"] == 2
