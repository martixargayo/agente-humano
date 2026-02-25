from __future__ import annotations

from .schemas import default_world_state


def update_world_state(prev_world: dict, user_message: str, **kwargs) -> tuple[dict, dict]:
    del prev_world, user_message, kwargs
    return default_world_state(), {"extractor_used": False}


def diff_world_state(prev_world: dict, world_state: dict) -> dict:
    if not isinstance(prev_world, dict) or not isinstance(world_state, dict):
        return {}
    if prev_world == world_state:
        return {}
    return {"changed": True}
