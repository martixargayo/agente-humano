from __future__ import annotations

import os

COMM_VISUAL_MODE_DEFAULT = 'metadata'
COMM_VISUAL_MAX_FRAMES = 90
COMM_VISUAL_BATCH_TARGET = 30
COMM_VISUAL_TAIL_MIN = 6
COMM_VISUAL_DETAIL = 'low'

COMM_VISUAL_OPENAI_MODEL_DEFAULT = 'gpt-4.1-mini'
COMM_VISUAL_OPENAI_TIMEOUT_S_DEFAULT = 25.0
COMM_VISUAL_OPENAI_MAX_RETRIES_DEFAULT = 2


def get_visual_mode() -> str:
    raw = (os.getenv('COMM_VISUAL_MODE') or '').strip().lower()
    if raw in {'metadata', 'llm_v1'}:
        return raw
    return COMM_VISUAL_MODE_DEFAULT


def is_visual_llm_enabled() -> bool:
    raw = (os.getenv('COMM_VISUAL_OPENAI_ENABLED') or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    return False


def get_visual_openai_model() -> str:
    return (os.getenv('COMM_VISUAL_OPENAI_MODEL') or '').strip() or COMM_VISUAL_OPENAI_MODEL_DEFAULT


def get_visual_openai_timeout_s() -> float:
    raw = (os.getenv('COMM_VISUAL_OPENAI_TIMEOUT_S') or '').strip()
    if not raw:
        return COMM_VISUAL_OPENAI_TIMEOUT_S_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return COMM_VISUAL_OPENAI_TIMEOUT_S_DEFAULT
    return value if value > 0 else COMM_VISUAL_OPENAI_TIMEOUT_S_DEFAULT


def get_visual_openai_max_retries() -> int:
    raw = (os.getenv('COMM_VISUAL_OPENAI_MAX_RETRIES') or '').strip()
    if not raw:
        return COMM_VISUAL_OPENAI_MAX_RETRIES_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return COMM_VISUAL_OPENAI_MAX_RETRIES_DEFAULT
    if value < 0:
        return COMM_VISUAL_OPENAI_MAX_RETRIES_DEFAULT
    return value
