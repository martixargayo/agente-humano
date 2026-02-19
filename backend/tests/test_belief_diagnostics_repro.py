from negotiation.belief_state_updater import update_belief_state
from negotiation.schemas import default_belief_state, default_world_state
from negotiation.world_state_updater import update_world_state


class _WorldDeps:
    def __init__(self, payloads: list[str]):
        self._payloads = payloads
        self._idx = 0

    def execute(self, _messages):
        payload = self._payloads[self._idx]
        self._idx += 1
        return payload


class _BeliefLLM:
    def invoke(self, _messages):
        return (
            '{"schema_version":"belief_updater_v2","universal_patch":{},"negotiation_patch":{},'
            '"belief_buckets_patch":{"hypotheses":[{"text":"Alta urgencia por liquidez hoy. (0.82)","confidence":0.82,"status":"active"}],'
            '"strategy_notes":[],"risk_flags":[],"watch_items":[]},"meta":{"schema_valid":true}}'
        )


def test_repro_two_turns_world_changes_and_belief_has_trace(monkeypatch):
    world_payloads = [
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"offers":[],"concessions":[{"text":"Dispuesto a hacer concesiones por dinero hoy.","confidence":0.7,"raw_text":"estoy dispuesto a hacer concesiones a cambio de dinero hoy","source_turn":1}],"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},"meta":{"negotiation_signal_detected":true,"extraction_quality":"high"}}',
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"offers":[{"text":"Acepta sacrificar dinero futuro por dinero hoy.","confidence":0.8,"raw_text":"concretamente estoy dispuesto a sacrificar dinero futuro a cambio de mas dinero hoy","source_turn":2}],"concessions":[],"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},"meta":{"negotiation_signal_detected":true,"extraction_quality":"high"}}',
    ]
    monkeypatch.setattr("negotiation.belief_state_updater.get_belief_llm", lambda: _BeliefLLM())

    w0 = default_world_state()
    b0 = default_belief_state()
    deps = _WorldDeps(world_payloads)

    w1, _m1 = update_world_state(w0, "estoy dispuesto a hacer concesiones a cambio de dinero hoy", turn_count=1, conversation_mode="general", deps=deps)
    w2, _m2 = update_world_state(w1, "concretamente estoy dispuesto a sacrificar dinero futuro a cambio de mas dinero hoy", turn_count=2, conversation_mode="general", deps=deps)

    assert len(w1["world_buckets"]["offers"]) == 0
    assert len(w2["world_buckets"]["offers"]) == 1

    b2, meta = update_belief_state(
        prev_belief_state=b0,
        prev_world_state=w1,
        world_state=w2,
        world_diff={"domain": {"world_buckets": {"before": w1["world_buckets"], "after": w2["world_buckets"]}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="concretamente estoy dispuesto a sacrificar dinero futuro a cambio de mas dinero hoy",
        context_snippet="",
        force_update=True,
        conversation_mode="negotiation",
    )

    assert meta.get("belief_llm_used") is True
    assert meta.get("belief_parse_ok") is True
    assert "belief_buckets_patch" in (meta.get("belief_patch_keys") or [])
    assert meta.get("belief_noop_reason", "") in {"", "merge_no_effect", "patch_empty", "parse_error"}
    assert meta.get("belief_merge_changed") is True or meta.get("belief_noop_reason") != ""
    assert "belief_buckets" in b2
