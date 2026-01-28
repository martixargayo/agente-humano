from negotiation.intent_manager import update_intent_state
from negotiation.phase_state_updater import update_phase_state
from negotiation.policy_planner import _POLICY_BY_ID, plan_policy
from negotiation.precedence import compute_precedence
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_progress_state,
    default_world_state,
)


class _StubPlanner:
    def __init__(self, payload: dict):
        self._payload = payload

    def with_structured_output(self, _model):
        return self

    def invoke(self, _messages):
        payload = dict(self._payload)

        class _Result:
            def model_dump(self_inner):
                return payload

        return _Result()


class _StubPrompt:
    def format_messages(self, **_kwargs):
        return []


def test_compute_precedence_recovery_guard_overrides_signals():
    world = default_world_state()
    world["price_firm"] = True
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "tense"

    prec = compute_precedence(world=world, belief=belief, intent=None)

    assert prec.mode == "recovery_guard"
    assert prec.phase_floor == "recovery"
    assert prec.allow_closing is False


def test_compute_precedence_discovery_on_claims():
    world = default_world_state()
    world["other_buyer_claimed"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "discovery"
    assert "credibility_check" in prec.min_policy_tags


def test_compute_precedence_price_firm_without_requirements():
    world = default_world_state()
    world["price_firm"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "bargaining"
    assert prec.allow_closing is False


def test_compute_precedence_price_firm_with_concession():
    world = default_world_state()
    world["price_firm"] = True
    world["concession_made"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "closing_push"
    assert prec.phase_floor == "closing"
    assert prec.allow_closing is True


def test_compute_precedence_concession_bargaining():
    world = default_world_state()
    world["price_mentioned"] = True
    world["concession_made"] = True

    prec = compute_precedence(world=world, belief=default_belief_state(), intent=None)

    assert prec.mode == "bargaining"


def test_phase_precedence_blocks_closing():
    world = default_world_state()
    world["price_firm"] = True
    belief = default_belief_state()
    phase, meta = update_phase_state(
        prev_phase_state=default_progress_state()["phase_state"],
        world_state=world,
        world_diff={"price_firm": {"before": False, "after": True}},
        belief_state=belief,
        intent_state=default_intent_state(),
        recent_history_text="",
        turn_count=3,
        precedence={"phase_floor": "recovery", "allow_closing": False},
    )

    assert phase["phase"] == "recovery"
    assert meta["phase_precedence_forced"] is True


def test_policy_planner_respects_precedence_tags(monkeypatch):
    from negotiation import policy_planner

    world = default_world_state()
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "tense"
    progress = default_progress_state()

    monkeypatch.setattr(
        policy_planner,
        "_planner_llm",
        _StubPlanner(
            {
                "policy_id": "deescalate_tension",
                "reason": "tension alta",
                "micro_goal": "bajar presión",
                "risk_posture": "low",
            }
        ),
    )
    monkeypatch.setattr(policy_planner, "_planner_prompt", _StubPrompt())

    decision, meta = plan_policy(
        world_state=world,
        belief_state=belief,
        progress_state=progress,
        intent_hint=None,
        precedence={
            "mode": "recovery_guard",
            "min_policy_tags": ["deescalation", "safe_when_tense"],
            "block_policy_tags": ["aggressive"],
        },
        objective="obj",
        constraints="",
        recent_context="",
    )

    allowed = meta.get("allowed_policy_ids", [])
    assert decision["policy_id"] == "deescalate_tension"
    assert meta["precedence_mode"] == "recovery_guard"
    assert all("aggressive" not in (_POLICY_BY_ID[pid].tags or set()) for pid in allowed)


def test_intent_pauses_under_recovery_guard():
    intent = default_intent_state()
    intent.update(
        {
            "status": "active",
            "intent_type": "closing",
            "steps": [
                {"kind": "close_next", "target_slot": "", "success_if_filled": []},
            ],
        }
    )
    updated, meta, _hint = update_intent_state(
        prev_intent=intent,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        user_message="",
        turn_count=2,
        precedence={"mode": "recovery_guard"},
    )

    assert updated["status"] == "paused"
    assert meta["intent_transition"] == "pause"
