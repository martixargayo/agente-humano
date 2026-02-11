from __future__ import annotations

import warnings

from ..legacy import intent_node as _legacy
from ..legacy.intent_node import *  # noqa: F403

warnings.warn(
    "negotiation.nodes.intent_node is deprecated; use negotiation.legacy.intent_node instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["intent_manager_node"]
