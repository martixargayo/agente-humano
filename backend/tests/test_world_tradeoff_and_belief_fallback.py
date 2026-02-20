from negotiation.belief_compat import merge_belief_buckets_update_not_rewrite, update_belief_state
from negotiation.gating.gate_world import gate_world
from negotiation.schemas import default_belief_state, default_world_state
from negotiation.world_state_updater import apply_world_skip_fallback


def test_gate_world_refreshes_every_non_empty_user_turn():
    skipped, reason, _meta = gate_world(
        user_message="estoy dispuesto a sacrificar dinero futuro para tener mas dinero hoy",
        turn_count=2,
        last_refresh_turn=2,
        prev_features={"len_bucket": "41_plus"},
        current_features={"len_bucket": "41_plus"},
        interval=3,
        modality="text",
        conversation_mode="general",
    )
    assert skipped is False
    assert reason == "always_refresh_user_turn"


def test_world_skip_fallback_keeps_state_without_semantic_backstop():
    prev = default_world_state()
    world, meta = apply_world_skip_fallback(
        prev,
        "menos dinero futuro a cambio de mas dinero hoy",
        turn_count=7,
    )
    assert meta.get("fallback_applied") is False
    assert meta.get("fallback_reasons") == []
    assert world.get("world_buckets", {}).get("offers", []) == []


def test_belief_update_uses_prepatch_when_llm_parse_fails(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ValueError("parse fail")

    monkeypatch.setattr(
        "negotiation.belief_compat.extract_belief_patch_llm_v3",
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
    assert belief == default_belief_state()
    assert meta.get("belief_fallback_reason") == "parse_error"


def test_merge_belief_buckets_prefers_update_not_rewrite():
    prev = {
        "hypotheses": [{"text": "Alta urgencia por liquidez hoy. (0.80)", "confidence": 0.8, "status": "active"}],
        "strategy_notes": [],
        "risk_flags": [],
        "watch_items": [],
    }
    patch = {
        "hypotheses": [{"text": "Alta urgencia por liquidez hoy. (0.86)", "confidence": 0.86, "status": "active"}],
        "strategy_notes": [{"text": "Pedir contrapartidas verificables.", "confidence": 0.7, "status": "new"}],
    }
    merged = merge_belief_buckets_update_not_rewrite(prev, patch)
    assert len(merged["hypotheses"]) == 1
    assert any("0.86" in h["text"] for h in merged["hypotheses"])
