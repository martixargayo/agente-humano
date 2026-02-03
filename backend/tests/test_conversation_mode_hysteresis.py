from negotiation.mode_inference import update_conversation_mode
from negotiation.schemas import default_progress_state, default_world_state


def test_conversation_mode_hysteresis():
    progress = default_progress_state()
    world = default_world_state()
    world.update(
        {
            "price_mentioned": True,
            "min_price_claimed": True,
            "deadline_claimed": True,
        }
    )

    progress = update_conversation_mode(progress, world, 1)
    assert progress["conversation_mode"] == "general"

    for turn in range(2, 7):
        progress = update_conversation_mode(progress, world, turn)

    assert progress["conversation_mode"] == "negotiation"

    world_clear = default_world_state()
    for turn in range(7, 10):
        progress = update_conversation_mode(progress, world_clear, turn)

    assert progress["conversation_mode"] == "general"
