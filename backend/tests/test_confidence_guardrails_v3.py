from negotiation.validation import normalize_world_buckets
from negotiation.world_state_updater import merge_world_buckets_append_mostly


def test_guardrail_rejects_zero_non_defaulted_after_merge():
    prev = {"world_buckets": {"offers": []}}
    patch = {"offers": [{"text": "Oferta cero", "confidence": 0.0, "raw_text": "oferta cero", "source_turn": 1}]}
    merged, _ = merge_world_buckets_append_mostly(prev, patch, turn_idx=1)
    item = merged["world_buckets"]["offers"][0]
    assert not (item["confidence"] == 0.0 and item["confidence_defaulted"] is False)


def test_missing_confidence_defaults_to_floor_and_marks_defaulted():
    buckets = normalize_world_buckets(
        {"offers": [{"text": "Oferta sin conf", "raw_text": "Oferta sin conf", "source_turn": 1}]},
        default_turn=1,
    )
    item = buckets["offers"][0]
    assert item["confidence_defaulted"] is True
    assert item["confidence"] >= 0.6


def test_invalid_confidence_defaults_to_floor_and_marks_defaulted():
    buckets = normalize_world_buckets(
        {"offers": [{"text": "Oferta invalida", "confidence": "NaN?", "raw_text": "Oferta invalida", "source_turn": 1}]},
        default_turn=1,
    )
    item = buckets["offers"][0]
    assert item["confidence_defaulted"] is True
    assert item["confidence"] == 0.6
