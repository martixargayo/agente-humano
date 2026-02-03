from .executor_prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_PROMPT, EXECUTOR_OUTPUT_SCHEMA
from .persona_profiles import get_persona_profile
from .scene_profiles import get_scene_profile
from .style_contracts import get_style_contract
from .render_contracts import RENDER_LIMITS, CRITICAL_VIOLATION_CODES


def resolve_render_profiles(render_state: dict) -> tuple[dict, dict, dict]:
    persona = get_persona_profile(render_state.get("persona_id", "default"))
    scene = get_scene_profile(render_state.get("scene_id", "default_chat"))
    style = get_style_contract(render_state.get("style_id", "default"))
    return persona, scene, style
