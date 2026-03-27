from __future__ import annotations

import os

_TRUTHY = {'1', 'true', 'yes', 'on'}
_FALSY = {'0', 'false', 'no', 'off'}


def parse_env_bool(name: str, *, default: bool = False) -> bool:
    raw = (os.getenv(name) or '').strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def parse_env_choice(name: str, *, allowed: set[str], default: str) -> str:
    raw = (os.getenv(name) or '').strip().lower()
    if raw in allowed:
        return raw
    return default
