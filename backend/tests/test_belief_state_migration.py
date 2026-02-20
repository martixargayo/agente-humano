from __future__ import annotations

from tests.legacy_fixtures.belief_contracts_legacy import UNIVERSAL_REASON_KEYS
from state import SessionState, get_session_state, save_session_state


def test_session_state_migrates_legacy_belief_state() -> None:
    state = SessionState(user_id="legacy", session_id="session")
    state.belief_state = {
        "dynamics": {"interaction_health": "tense"},
        "tom": {"other_goals": ["goal-a"]},
        "stance": {"seller_flexibility": 0.8},
        "reasons": {
            "tone_shift": {"weight": 0.7, "confidence": 0.6, "evidence": "x"},
            "price_signal": {"weight": 0.6, "confidence": 0.5, "evidence": "y"},
        },
        "hypotheses": ["hyp-1"],
        "evaluations": {"deal_feasibility": 0.2},
    }
    save_session_state(state)

    loaded = get_session_state("legacy", "session")
    belief = loaded.belief_state

    assert set(belief.keys()) == {"universal", "negotiation"}
    assert belief["universal"]["dynamics"]["interaction_health"] == "tense"
    assert belief["universal"]["tom"]["other_goals"] == ["goal-a"]
    assert belief["negotiation"]["stance"]["seller_flexibility"] == 0.8
    assert belief["negotiation"]["hypotheses"] == ["hyp-1"]
    assert belief["negotiation"]["evaluations"]["deal_feasibility"] == 0.2
    assert "tone_shift" in belief["universal"]["reasons"]
    assert "price_signal" in belief["negotiation"]["reasons"]
    assert "tone_shift" in UNIVERSAL_REASON_KEYS
