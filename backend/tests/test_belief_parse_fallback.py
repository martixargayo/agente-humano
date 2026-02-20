from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.telemetry.trace_runtime import init_trace_runtime


class _BrokenDeps:
    def execute(self, _messages):
        return '{"schema_version":"v3", "belief_buckets": {"hypotheses": [}'


def test_belief_parse_error_fallback_reuses_previous_state():
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

    out = belief_updater_node(
        {
            "deps": _BrokenDeps(),
            "trace_runtime": init_trace_runtime(),
            "belief_state": prev_belief,
            "prev_world_state": default_world_state(),
            "world_state": world,
            "world_diff": {"domain": {"world_buckets": {"before": {}, "after": world["world_buckets"]}}},
            "progress_state": default_progress_state(),
            "turn_count": 5,
            "user_message": "concretamente estoy dispuesto a sacrificar dinero futuro a cambio de tener dinero hoy",
        }
    )

    assert out["belief_state"] == prev_belief
    assert out["belief_update_meta"].get("belief_update_skipped") is True
    assert out["belief_update_meta"].get("skip_reason") == "belief_llm_error"
    assert out["trace_runtime"]["llm_calls"][0]["name"] == "belief_llm"
    assert out["trace_runtime"]["llm_calls"][0]["ok"] is False
