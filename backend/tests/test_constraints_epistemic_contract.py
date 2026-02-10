from negotiation.elementos.render.constraints_builder import build_constraints_struct


def test_constraints_builder_epistemic_precedence():
    out = build_constraints_struct(
        world={"negotiation": {}},
        belief={
            "universal": {
                "dynamics": {"interaction_health": "tense"},
                "behavior_guidance": {"verification_need": 0.9, "conflict_risk": 0.8, "epistemic_style": "hedged"},
            }
        },
        progress={"conversation_mode": "negotiation"},
        decision={"policy_id": "safe_neutral"},
        persona={},
        scene={},
        style={"max_questions": 3, "markdown_allowed": False},
    )
    assert out["max_questions"] == 1
    assert out["must_hedge"] is True
    assert out["verify_first"] is True
    assert out["epistemic_style"] == "hedged"
