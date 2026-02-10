from copy import deepcopy

from .executor_prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_PROMPT, EXECUTOR_OUTPUT_SCHEMA
from .persona_profiles import get_persona_profile
from .scene_profiles import get_scene_profile
from .style_contracts import get_style_contract
from .render_contracts import RENDER_LIMITS, CRITICAL_VIOLATION_CODES


def resolve_render_profiles(render_state: dict) -> tuple[dict, dict, dict]:
    persona = deepcopy(get_persona_profile(render_state.get("persona_id", "default")))
    scene = deepcopy(get_scene_profile(render_state.get("scene_id", "default_chat")))
    style = deepcopy(get_style_contract(render_state.get("style_id", "default")))

    persona_override = render_state.get("persona_profile")
    if isinstance(persona_override, dict):
        persona.update(deepcopy(persona_override))
    scene_override = render_state.get("scene_profile")
    if isinstance(scene_override, dict):
        scene.update(deepcopy(scene_override))
    style_override = render_state.get("style_contract")
    if isinstance(style_override, dict):
        style.update(deepcopy(style_override))
    return persona, scene, style
