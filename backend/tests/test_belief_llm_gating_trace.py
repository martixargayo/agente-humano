from datetime import datetime, timezone

from negotiation.nodes.belief_node import belief_updater_node
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.telemetry.live_trace import build_trace_event
from negotiation.telemetry.trace_runtime import init_trace_runtime
from state import SessionState


class _Deps:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    def execute(self, _messages):
        self.calls += 1
        return self.payload


def _state_for_node(*, prev_world: dict, world: dict, deps: _Deps):
    return {
        "deps": deps,
        "trace_runtime": init_trace_runtime(),
        "belief_state": default_belief_state(),
        "prev_world_state": prev_world,
        "world_state": world,
        "world_diff": {},
        "progress_state": default_progress_state(),
        "turn_count": 4,
        "user_message": "nuevo mensaje",
    }


def test_belief_skips_when_world_buckets_do_not_change():
    deps = _Deps("{}")
    prev_world = default_world_state()
    world = default_world_state()

    out = belief_updater_node(_state_for_node(prev_world=prev_world, world=world, deps=deps))

    assert deps.calls == 0
    assert out["belief_update_meta"]["belief_update_skipped"] is True
    assert out["belief_update_meta"]["skip_reason"] == "no_world_delta"
    llm_names = [item.get("name") for item in out["trace_runtime"]["llm_calls"]]
    assert "belief_llm" not in llm_names


def test_belief_runs_llm_when_world_buckets_change_and_records_timing():
    deps = _Deps(
        '{"schema_version":"v3","belief_buckets":{"hypotheses":[{"text":"Hay tensión","confidence":0.8,"status":"new"}],'
        '"strategy_notes":[],"risk_flags":[],"watch_items":[]},'
        '"planner_signals":{"interaction_health":"tense","conflict_risk":0.71,"recommended_move":"deescalate","recovery_mode":true}}'
    )
    prev_world = default_world_state()
    world = default_world_state()
    world["world_buckets"]["claims"] = [{"text": "sube presión", "confidence": 0.9, "raw_text": "sube presión", "source_turn": 4}]

    out = belief_updater_node(_state_for_node(prev_world=prev_world, world=world, deps=deps))

    assert deps.calls == 1
    assert out["belief_update_meta"]["belief_update_skipped"] is False
    llm_names = [item.get("name") for item in out["trace_runtime"]["llm_calls"]]
    assert "belief_llm" in llm_names
    assert out["trace_runtime"]["nodes"]["belief_updater"]["llm_ms"] > 0


def test_live_trace_belief_changed_keys_include_belief_buckets_when_executed():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 5,
        "belief_prev": default_belief_state(),
        "belief_new": {
            "schema_version": "v3",
            "belief_buckets": {
                "hypotheses": [{"text": "Cambio", "confidence": 0.8, "status": "new"}],
                "strategy_notes": [],
                "risk_flags": [],
                "watch_items": [],
            },
            "planner_signals": {
                "interaction_health": "tense",
                "conflict_risk": 0.7,
                "recommended_move": "deescalate",
                "recovery_mode": True,
            },
        },
        "belief_diff": {
            "belief_buckets": {
                "before": default_belief_state()["belief_buckets"],
                "after": {
                    "hypotheses": [{"text": "Cambio", "confidence": 0.8, "status": "new"}],
                    "strategy_notes": [],
                    "risk_flags": [],
                    "watch_items": [],
                },
            }
        },
    }

    event = build_trace_event(user_id="u1", session_id="s1", session=session, trace_index=0, trace_item=trace_item)

    assert "belief_buckets" in event["belief_changed_keys"]
