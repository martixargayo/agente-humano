from negotiation.schemas import default_belief_state
from negotiation.validation import normalize_belief_state


def test_belief_backward_compat_no_mirrors():
    belief = default_belief_state()
    normalized, _issues = normalize_belief_state(belief)
    assert "dynamics" not in normalized
    assert "tom" not in normalized
    assert "stance" not in normalized
