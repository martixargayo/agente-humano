from __future__ import annotations

import os
from typing import Iterable


def getenv_preferred(*, preferred: str, legacy: Iterable[str] = (), default: str) -> str:
    """Return env var value preferring a new name and falling back to legacy aliases."""
    value = os.getenv(preferred)
    if value:
        return value
    for key in legacy:
        legacy_value = os.getenv(key)
        if legacy_value:
            return legacy_value
    return default


def getenv_float_preferred(*, preferred: str, legacy: Iterable[str] = (), default: float) -> float:
    value = getenv_preferred(preferred=preferred, legacy=legacy, default=str(default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
