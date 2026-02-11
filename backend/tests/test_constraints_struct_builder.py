from negotiation.elementos.render.constraints_builder import build_constraints_struct
from negotiation.elementos.render import resolve_render_profiles
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def test_constraints_struct_builder_flags():
    world = default_world_state()
    belief = default_belief_state()
    belief["universal"]["dynamics"]["interaction_health"] = "tense"
    progress = default_progress_state()
    progress["conversation_mode"] = "negotiation"
    decision = {"policy_id": "info_extract_critical"}
    render_state = progress.get("render_state")
    persona, scene, style = resolve_render_profiles(render_state)

    constraints = build_constraints_struct(
        world=world,
        belief=belief,
        progress=progress,
        decision=decision,
        persona=persona,
        scene=scene,
        style=style,
    )

    assert "markdown" in constraints.get("forbid_formats", [])
    assert constraints.get("max_questions") == 1
    assert constraints.get("disallow_numbers") is True
    assert "price" in constraints.get("require_ask_if_missing", [])
