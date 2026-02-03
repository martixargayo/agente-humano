from negotiation.validation import normalize_belief_state


def test_belief_normalization_clamps_and_filters():
    raw = {
        "universal": {
            "metrics": {"trust": 2.0, "cooperation": -1.0, "clarity": 0.2, "engagement": 1.2},
            "dynamics": {"interaction_health": "wild", "escalation": "up", "looping": True, "evasion": False, "commitment": "hard"},
            "tom": {
                "other_goals": ["x" * 200] * 10,
                "other_tactics": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"],
                "other_belief_about_me": ["b"],
                "confidence": 2.5,
            },
            "reasons": {
                "tone_shift": {"weight": 2.0, "confidence": -1.0, "evidence_text": "e" * 300},
                "bad_key": {"weight": 0.5, "confidence": 0.5, "evidence_text": "x"},
            },
        },
        "negotiation": {},
    }
    belief, _issues = normalize_belief_state(raw)
    metrics = belief["universal"]["metrics"]
    assert 0.0 <= metrics["trust"] <= 1.0
    assert 0.0 <= metrics["cooperation"] <= 1.0
    reasons = belief["universal"]["reasons"]
    assert "bad_key" not in reasons
    assert len(reasons["tone_shift"]["evidence"]) <= 180
    tom = belief["universal"]["tom"]
    assert len(tom["other_goals"]) <= 6
    assert len(tom["other_goals"][0]) <= 80
