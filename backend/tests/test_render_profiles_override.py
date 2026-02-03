from negotiation.elementos.render import resolve_render_profiles
from negotiation.schemas import default_progress_state


def test_render_profiles_override():
    progress = default_progress_state()
    progress["render_state"] = {
        "persona_id": "avatar_sales",
        "scene_id": "in_person_negotiation",
        "style_id": "concise",
        "language": "es",
    }
    persona, scene, style = resolve_render_profiles(progress["render_state"])
    assert persona.get("persona_id") == "avatar_sales"
    assert scene.get("scene_id") == "in_person_negotiation"
    assert style.get("style_id") == "concise"
