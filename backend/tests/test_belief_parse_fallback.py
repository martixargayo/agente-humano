from negotiation.belief_state_updater import update_belief_state
from negotiation.schemas import default_belief_state, default_world_state


class _BrokenBeliefLLM:
    def invoke(self, _messages):
        # Missing comma between "status" and "meta" (JSON inválido)
        return '{"schema_version":"belief_updater_v2","universal_patch":{},"negotiation_patch":{},"belief_buckets_patch":{"hypotheses":[{"text":"Alta urgencia por liquidez hoy. (0.85)","confidence":0.85,"status":"active"}] "meta":{"schema_valid":true}}'


def test_belief_parse_error_fallback_is_safe_and_traceable(monkeypatch):
    monkeypatch.setattr(
        "negotiation.belief_state_updater.get_belief_llm",
        lambda: _BrokenBeliefLLM(),
    )

    prev_belief = default_belief_state()
    world = default_world_state()
    world["world_buckets"]["offers"] = [
        {
            "text": "Propone intercambio: más dinero hoy por valor futuro.",
            "confidence": 0.7,
            "raw_text": "estoy dispuesto a sacrificar dinero futuro a cambio de tener dinero hoy",
            "source_turn": 5,
        }
    ]

    belief, meta = update_belief_state(
        prev_belief_state=prev_belief,
        prev_world_state=default_world_state(),
        world_state=world,
        world_diff={"domain": {"world_buckets": {"before": {}, "after": world["world_buckets"]}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="concretamente estoy dispuesto a sacrificar dinero futuro a cambio de tener dinero hoy",
        context_snippet="",
        force_update=True,
        conversation_mode="negotiation",
    )

    assert belief == prev_belief
    assert meta.get("belief_fallback_used") is True
    assert meta.get("belief_fallback_reason") == "parse_error"
    assert "Expecting ',' delimiter" in meta.get("belief_error", "")
