from negotiation.schemas import default_world_state
from negotiation.perception.interaction_signals import extract_interaction_signals


def test_negated_acceptance_does_not_trigger():
    prev_world = default_world_state()
    for message in ("no me parece bien", "vale, pero no", "ok, no"):
        interaction = extract_interaction_signals(message, prev_world)
        assert interaction["implicit_acceptance"] is False
