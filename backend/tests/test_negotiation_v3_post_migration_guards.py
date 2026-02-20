from __future__ import annotations

from datetime import datetime, timezone

from negotiation.schemas import default_world_state
from negotiation.telemetry.live_trace import build_trace_event
from negotiation.world_state_updater import update_world_state
from state import SessionState


class _FakeDeps:
    def __init__(self, payload: str):
        self._payload = payload

    def execute(self, _messages):
        return self._payload


LEGACY_TOKENS = {
    "universal_domain",
    "negotiation_v2",
    "universal_v2",
    "universal_state",
    "open_claims",
    "evidence_items",
    "world_observations",
    "world_derived",
    "intent_step",
    "intent_transition",
}


def test_live_trace_payload_has_no_legacy_keys_in_event_tree():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item={
            "turn": 1,
            "world_prev": {"schema_version": "v3", "world_buckets": {}, "world_state_meta": {}},
            "world_new": {"schema_version": "v3", "world_buckets": {}, "world_state_meta": {}},
            "belief_prev": {"schema_version": "v3", "belief_buckets": {}, "planner_signals": {}},
            "belief_new": {"schema_version": "v3", "belief_buckets": {}, "planner_signals": {}},
            "gates": {"world_skipped": False, "belief_skipped": True, "planner_skipped": False},
        },
    )

    flat = str(event)
    for token in LEGACY_TOKENS:
        assert token not in flat


def test_updated_fields_and_turn_idx_reflect_current_update_turn():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v4","world_buckets_patch":{"offers":[{"text":"Oferta 1","confidence":0.7,"raw_text":"oferta 1","source_turn":4}],"concessions":[],"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},"meta":{}}'
    )
    prev = default_world_state()
    prev["world_state_meta"]["turn_idx"] = 3

    world, meta = update_world_state(prev, "oferta 1", turn_count=4, conversation_mode="general", deps=deps)

    assert world["world_state_meta"]["turn_idx"] == 4
    assert world["world_state_meta"]["updated_fields"] == ["world_buckets.offers"]
    assert meta["updated_buckets"] == ["offers"]
