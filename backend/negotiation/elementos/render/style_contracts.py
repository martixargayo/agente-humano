from __future__ import annotations

from typing import Dict

from ...schemas import StyleContract


_STYLES: Dict[str, StyleContract] = {
    "default": {
        "style_id": "default",
        "target_length": "short",
        "format": "plain",
        "max_questions": 2,
        "emoji_policy": "rare",
        "markdown_allowed": False,
    },
    "brief": {
        "style_id": "brief",
        "target_length": "short",
        "format": "plain",
        "max_questions": 1,
        "emoji_policy": "never",
        "markdown_allowed": False,
    },
}


def get_style(style_id: str | None) -> StyleContract:
    if not style_id:
        return dict(_STYLES["default"])
    return dict(_STYLES.get(style_id, _STYLES["default"]))
