from __future__ import annotations

from typing import Dict

from ...schemas import SceneProfile
from .carlos_buyer_preset import CARLOS_SCENE_PROFILE


_SCENES: Dict[str, SceneProfile] = {
    "default_chat": {
        "scene_id": "default_chat",
        "setting": "chat app",
        "macro_goal": "help the user with their objective",
        "operational_context": ["chat_only", "no_internal_systems"],
        "disclaimers": ["chat_only", "no_internal_systems"],
    },
    "in_person_negotiation": {
        "scene_id": "in_person_negotiation",
        "setting": "in-person negotiation",
        "macro_goal": "reach a fair agreement",
        "operational_context": ["in_person", "no_internal_systems"],
        "disclaimers": ["no_internal_systems"],
    },
    "mustang67_in_person_viewing": CARLOS_SCENE_PROFILE,
}


def get_scene_profile(scene_id: str | None) -> SceneProfile:
    if not scene_id:
        return dict(_SCENES["default_chat"])
    return dict(_SCENES.get(scene_id, _SCENES["default_chat"]))
