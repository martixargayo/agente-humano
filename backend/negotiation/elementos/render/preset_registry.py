from __future__ import annotations

import os
from copy import deepcopy
from typing import Literal, TypedDict

from ...schemas import default_render_state


class BuyerPreset(TypedDict):
    preset_id: str
    persona_id: str
    scene_id: str
    style_id: str


PresetSource = Literal["explicit", "env", "none"]


_BUYER_PRESETS: dict[str, BuyerPreset] = {
    "carlos": {
        "preset_id": "carlos",
        "persona_id": "buyer_mustang67_v1",
        "scene_id": "mustang67_in_person_viewing",
        "style_id": "psyplay_compact",
    }
}


_DEFAULT_ENV_VAR = "NEGOTIATION_BUYER_PRESET"


def list_buyer_presets() -> list[str]:
    return sorted(_BUYER_PRESETS.keys())


def get_buyer_preset(preset_id: str | None) -> BuyerPreset | None:
    if not preset_id:
        return None
    return deepcopy(_BUYER_PRESETS.get(str(preset_id).strip().lower()))


def resolve_runtime_buyer_preset(explicit_preset_id: str | None = None) -> str | None:
    if explicit_preset_id:
        return str(explicit_preset_id).strip().lower()
    env_value = os.getenv(_DEFAULT_ENV_VAR, "").strip().lower()
    return env_value or None


def resolve_runtime_buyer_preset_choice(explicit_preset_id: str | None = None) -> tuple[str | None, PresetSource]:
    if explicit_preset_id:
        return str(explicit_preset_id).strip().lower(), "explicit"
    env_value = os.getenv(_DEFAULT_ENV_VAR, "").strip().lower()
    if env_value:
        return env_value, "env"
    return None, "none"


def apply_buyer_preset_to_render_state(
    progress_state: dict | None,
    preset_id: str | None,
    *,
    override_existing: bool = False,
    preset_source: PresetSource = "none",
) -> tuple[dict, dict]:
    progress = dict(progress_state or {})

    default_rs = default_render_state()
    incoming = dict(progress.get("render_state") or {})
    render_state = {**default_rs, **incoming}

    meta = {
        "buyer_preset_requested": preset_id or "",
        "buyer_preset_source": preset_source,
        "buyer_preset_applied": False,
        "buyer_preset_error": "",
    }

    preset = get_buyer_preset(preset_id)
    if not preset:
        if preset_id:
            meta["buyer_preset_error"] = "unknown_buyer_preset"
        progress["render_state"] = render_state
        return progress, meta

    already_customized = (
        render_state["persona_id"] != default_rs["persona_id"]
        or render_state["scene_id"] != default_rs["scene_id"]
        or render_state["style_id"] != default_rs["style_id"]
    )
    if already_customized and not override_existing:
        progress["render_state"] = render_state
        meta["buyer_preset_error"] = "render_state_already_customized"
        return progress, meta

    render_state["persona_id"] = preset["persona_id"]
    render_state["scene_id"] = preset["scene_id"]
    render_state["style_id"] = preset["style_id"]
    render_state["buyer_preset_id"] = preset["preset_id"]
    progress["render_state"] = render_state
    meta["buyer_preset_applied"] = True
    return progress, meta
