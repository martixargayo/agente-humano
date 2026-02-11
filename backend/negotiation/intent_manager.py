from __future__ import annotations

import warnings

from .legacy import intent_manager as _legacy
from .legacy.intent_manager import *  # noqa: F403

warnings.warn(
    "negotiation.intent_manager is deprecated; use negotiation.legacy.intent_manager instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = _legacy.__all__
