from negotiation.world_state_updater import merge_universal_state


def test_merge_goal_prefers_higher_confidence():
    prev = {"goal": {"summary": "A", "confidence": 0.8, "evidence_text": "x"}}
    patch_low = {"goal": {"summary": "B", "confidence": 0.6, "evidence_text": "y"}}
    patch_high = {"goal": {"summary": "C", "confidence": 0.9, "evidence_text": "z"}}

    out_low = merge_universal_state(prev, patch_low)
    assert out_low["goal"]["summary"] == "A"

    out_high = merge_universal_state(prev, patch_high)
    assert out_high["goal"]["summary"] == "C"


def test_constraints_dedupe_by_kind_key_value_polarity():
    prev = {
        "constraints": [
            {
                "kind": "time",
                "key": "availability",
                "value": "mañana",
                "polarity": "must",
                "confidence": 0.5,
                "evidence_text": "x",
            }
        ]
    }
    patch = {
        "constraints": [
            {
                "kind": "time",
                "key": "availability",
                "value": "mañana",
                "polarity": "must",
                "confidence": 0.8,
                "evidence_text": "y",
            }
        ]
    }
    out = merge_universal_state(prev, patch)
    assert len(out["constraints"]) == 1


def test_list_limits_enforced():
    patch = {
        "constraints": [
            {
                "kind": "time",
                "key": f"k{i}",
                "value": "x",
                "polarity": "must",
                "confidence": 0.5,
                "evidence_text": "e",
            }
            for i in range(30)
        ]
    }
    out = merge_universal_state({}, patch)
    assert len(out["constraints"]) == 10
