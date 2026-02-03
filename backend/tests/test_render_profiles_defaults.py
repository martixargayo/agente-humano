from negotiation.elementos.render import resolve_render_profiles
from negotiation.schemas import default_progress_state


def test_render_profiles_defaults():
    progress = default_progress_state()
    render_state = progress.get("render_state") or {}
    assert render_state.get("persona_id")
    assert render_state.get("scene_id")
    assert render_state.get("style_id")

    persona, scene, style = resolve_render_profiles(render_state)
    assert persona.get("persona_id") == "default"
    assert scene.get("scene_id") == "default_chat"
    assert style.get("markdown_allowed") is False
