from negotiation.schemas import default_belief_state
from negotiation.validation import normalize_belief_state


def test_belief_backward_compat_mirrors():
    belief = default_belief_state()
    normalized, _issues = normalize_belief_state(belief)
    assert normalized["dynamics"]["interaction_health"] == normalized["universal"]["dynamics"]["interaction_health"]
    assert normalized["tom"] == normalized["universal"]["tom"]
    assert normalized["stance"] == normalized["negotiation"]["stance"]
