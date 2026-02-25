from __future__ import annotations

from copy import deepcopy

from .executor_prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_PROMPT, EXECUTOR_OUTPUT_SCHEMA
from .persona_profiles import get_persona_profile
from .scene_profiles import get_scene_profile
from .style_contracts import get_style_contract
from .carlos_buyer_preset import CARLOS_PERSONA_PROFILE, CARLOS_SCENE_PROFILE, CARLOS_STYLE_CONTRACT


def resolve_render_profiles(render_state: dict):
    rs = render_state if isinstance(render_state, dict) else {}
    persona_id = str(rs.get("persona_id") or "").strip()
    scene_id = str(rs.get("scene_id") or "").strip()
    style_id = str(rs.get("style_id") or "").strip()

    if persona_id in {"", "default"}:
        persona = deepcopy(CARLOS_PERSONA_PROFILE)
    else:
        persona = get_persona_profile(persona_id)
        if str(persona.get("persona_id") or "default") == "default":
            persona = deepcopy(CARLOS_PERSONA_PROFILE)

    if scene_id in {"", "default"}:
        scene = deepcopy(CARLOS_SCENE_PROFILE)
    else:
        scene = get_scene_profile(scene_id)
        if str(scene.get("scene_id") or "default") in {"default", "default_chat"}:
            scene = deepcopy(CARLOS_SCENE_PROFILE)

    if style_id in {"", "default"}:
        style = deepcopy(CARLOS_STYLE_CONTRACT)
    else:
        style = get_style_contract(style_id)
        if str(style.get("style_id") or "default") == "default":
            style = deepcopy(CARLOS_STYLE_CONTRACT)

    return persona, scene, style


__all__ = [
    "EXECUTOR_SYSTEM_PROMPT",
    "EXECUTOR_USER_PROMPT",
    "EXECUTOR_OUTPUT_SCHEMA",
    "resolve_render_profiles",
]
