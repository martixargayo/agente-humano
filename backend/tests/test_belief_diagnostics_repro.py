from negotiation.extractors.belief_extractor_v1 import extract_belief_state_llm_v1
from negotiation.schemas import default_belief_state, default_world_state


class _Deps:
    def __init__(self, payload: str):
        self.payload = payload

    def execute(self, _messages):
        return self.payload


def test_belief_extractor_v1_normalizes_schema_and_signals():
    deps = _Deps(
        '{"schema_version":"legacy","belief_buckets":{"hypotheses":[{"text":"' + ('x' * 250) + '","confidence":2,"status":"weird"}]'
        ',"strategy_notes":[],"risk_flags":[],"watch_items":[]},'
        '"planner_signals":{"interaction_health":"bad","conflict_risk":2,"recommended_move":"foo","recovery_mode":"yes"},"legacy":{}}'
    )

    belief, meta = extract_belief_state_llm_v1(
        deps=deps,
        user_message="mensaje",
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        turn_idx=3,
    )

    assert belief["schema_version"] == "v3"
    assert len(belief["belief_buckets"]["hypotheses"][0]["text"]) <= 180
    assert belief["belief_buckets"]["hypotheses"][0]["status"] == "active"
    assert belief["planner_signals"]["conflict_risk"] == 1.0
    assert belief["planner_signals"]["recommended_move"] == "hold"
    assert meta["belief_engine"] == "llm_belief_extractor_v1"


def test_belief_extractor_v1_limits_world_context():
    world = default_world_state()
    world["world_buckets"]["offers"] = [
        {"text": f"offer-{i}", "confidence": 0.8, "raw_text": f"offer-{i}", "source_turn": 1}
        for i in range(20)
    ]
    deps = _Deps(
        '{"schema_version":"v3","belief_buckets":{"hypotheses":[],"strategy_notes":[],"risk_flags":[],"watch_items":[]},'
        '"planner_signals":{"interaction_health":"stable","conflict_risk":0.1,"recommended_move":"hold","recovery_mode":false}}'
    )

    belief, _meta = extract_belief_state_llm_v1(
        deps=deps,
        user_message="hola",
        world_state=world,
        prev_belief_state=default_belief_state(),
        turn_idx=1,
    )

    assert belief["schema_version"] == "v3"
