from __future__ import annotations

from typing import Dict

from .carlos_buyer_preset import CARLOS_STYLE_CONTRACT


_STYLES: Dict[str, dict] = {
    "default": {
        "style_id": "default",
        "target_length": "short",
        "format": "plain",
        "max_questions": 2,
        "emoji_policy": "rare",
        "markdown_allowed": False,
        "bullets_max": 4,
    },
    "concise": {
        "style_id": "concise",
        "target_length": "short",
        "format": "plain",
        "max_questions": 1,
        "emoji_policy": "never",
        "markdown_allowed": False,
        "bullets_max": 3,
    },
    "bullet_help": {
        "style_id": "bullet_help",
        "target_length": "medium",
        "format": "bullets",
        "max_questions": 1,
        "emoji_policy": "rare",
        "markdown_allowed": True,
        "bullets_max": 4,
    },
    "psyplay_compact": CARLOS_STYLE_CONTRACT,
}


def get_style_contract(style_id: str | None) -> dict:
    if not style_id:
        return dict(_STYLES["default"])
    return dict(_STYLES.get(style_id, _STYLES["default"]))
