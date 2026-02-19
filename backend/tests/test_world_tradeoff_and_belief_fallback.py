from negotiation.belief_state_updater import update_belief_state
from negotiation.gating.gate_world import gate_world
from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.world_state_updater import apply_world_skip_fallback


def test_gate_world_breaks_interval_hold_on_tradeoff_language():
    skipped, reason, meta = gate_world(
        user_message="menos dinero futuro a cambio de mas dinero hoy",
        turn_count=2,
        last_refresh_turn=2,
        prev_features={"len_bucket": "41_plus"},
        current_features={"len_bucket": "41_plus"},
        interval=3,
        modality="text",
        conversation_mode="general",
    )
    assert skipped is False
    assert reason == "semantic_tradeoff_trigger"
    assert "semantic_tradeoff_trigger" in (meta.get("changed_keys") or [])


def test_gate_world_detects_tradeoff_with_typo_sacrficar():
    skipped, reason, _meta = gate_world(
        user_message="estoy dispuesto a sacrficar dinero futuro para tener mas dinero hoy",
        turn_count=2,
        last_refresh_turn=2,
        prev_features={"len_bucket": "41_plus"},
        current_features={"len_bucket": "41_plus"},
        interval=3,
        modality="text",
        conversation_mode="general",
    )
    assert skipped is False
    assert reason == "semantic_tradeoff_trigger"


def test_world_skip_fallback_populates_negotiation_v2_terms():
    prev = default_world_state()
    world, meta = apply_world_skip_fallback(
        prev,
        "menos dinero futuro a cambio de mas dinero hoy",
        turn_count=7,
    )
    assert meta.get("fallback_applied") is True
    assert "offer_tradeoff_backstop" in (meta.get("fallback_reasons") or [])
    assert len(world.get("negotiation_v2", {}).get("offers", [])) >= 1
    assert world.get("negotiation_v2", {}).get("subject", {}).get("item")
    assert world.get("world_state_meta", {}).get("last_update_source") == "fallback"


def test_belief_update_uses_prepatch_when_llm_parse_fails(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ValueError("parse fail")

    monkeypatch.setattr(
        "negotiation.belief_state_updater.extract_belief_patch_llm_v3",
        _raise,
    )

    world = default_world_state()
    world["negotiation"]["urgency_claimed"] = True
    world["negotiation"]["urgency_reason"] = "time_pressure"
    world["negotiation"]["urgency_text"] = "necesito cerrar hoy"
    belief, meta = update_belief_state(
        prev_belief_state=default_belief_state(),
        prev_world_state=default_world_state(),
        world_state=world,
        world_diff={"domain": {"urgency_claimed": {"before": False, "after": True}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="necesito dinero",
        context_snippet="",
        force_update=True,
        conversation_mode="general",
    )
    assert meta.get("belief_llm_failed") is True
    assert meta.get("belief_updated_via_fallback") is True
    assert belief["negotiation"]["stance"]["time_pressure"] > 0.5


def test_belief_node_force_by_stale_urgency(monkeypatch):
    called = {"n": 0}

    def _fake_update_belief_state(**_kwargs):
        called["n"] += 1
        return default_belief_state(), {"belief_update_failed": False, "belief_update_skipped": False}

    world = default_world_state()
    world["negotiation"]["urgency_claimed"] = True
    progress = default_progress_state()
    progress["gate_state"]["last_belief_time_pressure_change_turn"] = 0

    state = {
        "deps": type("Deps", (), {"update_belief_state": staticmethod(_fake_update_belief_state)})(),
        "belief_state": default_belief_state(),
        "prev_world_state": default_world_state(),
        "world_state": world,
        "world_diff": {},
        "progress_state": progress,
        "turn_count": 3,
        "conversation_mode": "general",
        "extractor_meta": {"backstop_reasons": []},
        "last_policy_executed": None,
        "last_assistant_message": "",
        "user_message": "quiero dinero hoy",
        "recent_history_text": "",
    }

    out = belief_updater_node(state)
    assert called["n"] == 1
    assert out["belief_update_meta"].get("forced_by_stale_urgency") is True
