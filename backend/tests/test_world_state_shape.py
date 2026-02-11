from negotiation.schemas import default_world_state


def test_world_state_has_sections_and_no_interaction():
    world = default_world_state()
    assert "universal_domain" in world
    assert "negotiation" in world
    assert "interaction" not in world
