from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.telemetry.trace_runtime import init_trace_runtime


class _Deps:
    def __init__(self):
        self.calls = 0

    def execute(self, _messages):
        self.calls += 1
        return (
            '{"schema_version":"v3","belief_buckets":{"hypotheses":[{"text":"Detecta concesión","confidence":0.8,"status":"new"}],'
            '"strategy_notes":[],"risk_flags":[],"watch_items":[]},'
            '"planner_signals":{"interaction_health":"tense","conflict_risk":0.55,"recommended_move":"tradeoff","recovery_mode":false}}'
        )


def test_belief_node_runs_llm_when_world_buckets_change():
    deps = _Deps()
    prev_world = default_world_state()
    curr_world = default_world_state()
    curr_world["world_buckets"]["concessions"] = [
        {
            "text": "Ofrece papeleo gratis por más dinero hoy.",
            "confidence": 0.8,
            "raw_text": "si me pagas más hoy, te hago el papeleo gratis",
            "source_turn": 2,
        }
    ]
    state = {
        "deps": deps,
        "trace_runtime": init_trace_runtime(),
        "belief_state": default_belief_state(),
        "prev_world_state": prev_world,
        "world_state": curr_world,
        "world_diff": {},
        "progress_state": default_progress_state(),
        "turn_count": 2,
        "user_message": "si me pagas más hoy, te hago el papeleo gratis",
    }

    out = belief_updater_node(state)
    assert deps.calls == 1
    assert out["belief_update_meta"].get("belief_update_skipped") is False
    llm_names = [item.get("name") for item in out["trace_runtime"]["llm_calls"]]
    assert "belief_llm" in llm_names
