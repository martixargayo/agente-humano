from negotiation.schemas import default_world_state
from negotiation.world_state_updater import merge_world_buckets_append_mostly, update_world_state


class _FakeDeps:
    def __init__(self, payload: str):
        self._payload = payload

    def execute(self, _messages):
        return self._payload


def test_world_extractor_updates_world_buckets_and_trace_meta():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v4",'
        '"world_buckets_patch":{'
        '"offers":[{"text":"Propone intercambio hoy por ITV","confidence":0.8,"raw_text":"si me pagas más hoy, yo te pago la ITV 2 años","source_turn":1}],'
        '"concessions":[{"text":"Paga ITV 2 años si recibe más hoy","confidence":0.8,"raw_text":"si me pagas más hoy, yo te pago la ITV 2 años","source_turn":1}],'
        '"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},'
        '"meta":{"negotiation_signal_detected":true,"extraction_quality":"high"}}'
    )
    world, meta = update_world_state(
        default_world_state(),
        "si me pagas más hoy, yo te pago la ITV 2 años",
        turn_count=1,
        conversation_mode="general",
        deps=deps,
    )
    assert len(world["world_buckets"]["offers"]) == 1
    assert "world_buckets.offers" in world["world_state_meta"]["updated_fields"]
    assert meta["updated_buckets"] == ["offers", "concessions"]


def test_world_bucket_merge_dedupes_exact_raw_text():
    prev = default_world_state()
    prev["world_buckets"]["offers"] = [
        {
            "text": "Intercambio A",
            "confidence": 0.6,
            "raw_text": "si me pagas más hoy",
            "source_turn": 1,
        }
    ]
    patch = {
        "offers": [
            {
                "text": "Intercambio A mejor",
                "confidence": 0.9,
                "raw_text": "si me pagas más hoy",
                "source_turn": 2,
            }
        ]
    }
    merged, updated = merge_world_buckets_append_mostly(prev, patch, turn_idx=2)
    assert len(merged["world_buckets"]["offers"]) == 1
    assert merged["world_buckets"]["offers"][0]["confidence"] == 0.9
    assert updated == []
