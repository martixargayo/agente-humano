from negotiation.belief_state_updater import update_belief_state
from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.telemetry.live_trace import build_trace_event
from negotiation.telemetry.trace import diff_belief_state


class _LLMValid:
    model = "belief-test-model"

    def invoke(self, _messages):
        return (
            '{"schema_version":"belief_updater_v2","universal_patch":{},"negotiation_patch":{},'
            '"belief_buckets_patch":{"hypotheses":[{"text":"Urgencia alta de caja.","confidence":0.8,"status":"active"}],'
            '"strategy_notes":[],"risk_flags":[],"watch_items":[]},"meta":{"schema_valid":true}}'
        )


class _LLMInvalid:
    def invoke(self, _messages):
        return '{"schema_version":"belief_updater_v2","belief_buckets_patch":{"hypotheses":[{"text":"x" "confidence":0.8}]}}'


class _LLMNoop:
    def invoke(self, _messages):
        return (
            '{"schema_version":"belief_updater_v2","universal_patch":{},"negotiation_patch":{},'
            '"belief_buckets_patch":{"hypotheses":[{"text":"ya existe","confidence":0.7,"status":"active"}],'
            '"strategy_notes":[],"risk_flags":[],"watch_items":[]},"meta":{"schema_valid":true}}'
        )


class _Session:
    def __init__(self):
        from datetime import datetime

        self.last_updated = datetime.now()


def test_two_turns_belief_node_and_live_trace_debug(monkeypatch):
    monkeypatch.setattr("negotiation.belief_state_updater.get_belief_llm", lambda: _LLMValid())
    prev_world = default_world_state()
    curr_world = default_world_state()
    curr_world["world_buckets"]["offers"] = [
        {"text": "Oferta nueva", "confidence": 0.9, "raw_text": "oferta", "source_turn": 2}
    ]

    progress = default_progress_state()
    progress["gate_state"]["last_belief_refresh_turn"] = 1
    progress["gate_state"]["world_buckets_fingerprint_prev"] = "oldfp"

    state = {
        "belief_state": default_belief_state(),
        "prev_world_state": prev_world,
        "world_state": curr_world,
        "world_diff": {"domain": {"world_buckets": {"before": prev_world["world_buckets"], "after": curr_world["world_buckets"]}}},
        "progress_state": progress,
        "turn_count": 2,
        "conversation_mode": "negotiation",
        "extractor_meta": {},
        "last_policy_executed": None,
        "last_assistant_message": "",
        "user_message": "te propongo una oferta",
        "recent_history_text": "",
    }

    out = belief_updater_node(state)
    meta = out["belief_update_meta"]
    assert meta["belief_node_entered"] is True
    assert meta["belief_updater_invoked"] is True
    assert meta["belief_llm_used"] is True
    assert meta["belief_llm_raw_response_preview"]

    belief_diff = diff_belief_state(default_belief_state(), out["belief_state"])
    assert "belief_buckets" in belief_diff

    trace_item = {
        "turn": 2,
        "assistant_reply": "ok",
        "user_message": "hola",
        "belief_prev": default_belief_state(),
        "belief_new": out["belief_state"],
        "world_prev": prev_world,
        "world_new": curr_world,
        "belief_update_meta": meta,
        "gates": {},
        "planner_meta": {},
    }
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")
    event = build_trace_event(user_id="u", session_id="s", session=_Session(), trace_index=0, trace_item=trace_item)
    assert event["build_git_sha"] == "abc123"
    assert "belief" in event["trace"]["debug"]
    assert event["trace"]["debug"]["belief"]["belief_node_entered"] is True


def test_parse_error_exposes_exact_error_and_no_state_change(monkeypatch):
    monkeypatch.setattr("negotiation.belief_state_updater.get_belief_llm", lambda: _LLMInvalid())
    prev = default_belief_state()
    world = default_world_state()

    new_state, meta = update_belief_state(
        prev_belief_state=prev,
        prev_world_state=world,
        world_state=world,
        world_diff={"domain": {"world_buckets": {"before": {}, "after": {"offers": [{"text": "x"}]}}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="x",
        context_snippet="",
        force_update=True,
        conversation_mode="negotiation",
    )

    assert meta["belief_parse_ok"] is False
    assert "Expecting ',' delimiter" in meta["belief_parse_error"]
    assert meta["belief_noop_reason"] == "parse_error"
    assert new_state == prev


def test_merge_no_effect_sets_noop_reason(monkeypatch):
    monkeypatch.setattr("negotiation.belief_state_updater.get_belief_llm", lambda: _LLMNoop())
    prev = default_belief_state()
    world = default_world_state()

    seeded_state, _ = update_belief_state(
        prev_belief_state=prev,
        prev_world_state=world,
        world_state=world,
        world_diff={"domain": {"world_buckets": {"before": {}, "after": {"offers": [{"text": "x"}]}}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="x",
        context_snippet="",
        force_update=True,
        conversation_mode="negotiation",
    )

    new_state, meta = update_belief_state(
        prev_belief_state=seeded_state,
        prev_world_state=world,
        world_state=world,
        world_diff={"domain": {"world_buckets": {"before": {}, "after": {"offers": [{"text": "x"}]}}}},
        last_policy_executed=None,
        last_assistant_message="",
        user_message="x",
        context_snippet="",
        force_update=True,
        conversation_mode="negotiation",
    )

    assert meta["belief_merge_changed"] is False
    assert meta["belief_noop_reason"] == "merge_no_effect"
    assert new_state == seeded_state
