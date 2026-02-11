from negotiation.validation import normalize_world_state_v2, normalize_belief_state_v2


def test_normalize_world_state_v2_drops_invalid_and_clamps():
    raw = {
        "schema_version": "v2",
        "universal_domain": {},
        "negotiation": {},
        "universal_v2": {
            "affect": {"tone": "INVALID", "confidence": 7},
            "clarity": {"is_vague": "yes", "missing_info": ["a"]},
        },
        "negotiation_v2": {
            "offers": [{"side": "seller", "kind": "price", "status": "bad", "confidence": 4}],
            "evidence": [{"type": "doc", "items": ["x"], "status": "claimed", "confidence": -1, "meta": {"a": {"b": {"c": {"d": "e"}}}}}],
        },
    }
    out, _ = normalize_world_state_v2(raw)
    assert out["schema_version"] == "v2"
    assert out["universal_v2"]["affect"]["tone"] == "neutral"
    assert out["universal_v2"]["affect"]["confidence"] == 1.0
    assert out["negotiation_v2"]["offers"][0]["status"] == "proposed"
    assert out["negotiation_v2"]["evidence"][0]["confidence"] == 0.0


def test_normalize_belief_state_v2_filters_reasons_and_hypotheses():
    raw = {
        "schema_version": "v2",
        "universal": {
            "tom": {
                "hypotheses": [
                    {"kind": "bluff", "text": "x", "confidence": 3, "evidence_refs": ["e1"]},
                    "bad",
                ]
            }
        },
        "negotiation": {
            "stance": {"flexibility": 2, "unknown": 0.5},
            "reasons": {
                "constraint_signal": {"weight": 2, "confidence": -1, "evidence": "ok"},
                "unknown": {"weight": 1, "confidence": 1, "evidence": "bad"},
                "risk_signal": {"weight": 1, "confidence": 1, "evidence": ""},
            },
        },
    }
    out, _ = normalize_belief_state_v2(raw)
    assert out["negotiation"]["stance"]["flexibility"] == 1.0
    assert "unknown" not in out["negotiation"]["stance"]
    assert "constraint_signal" in out["negotiation"]["reasons"]
    assert "risk_signal" not in out["negotiation"]["reasons"]
    assert out["universal"]["tom"]["hypotheses"][0]["confidence"] == 1.0
