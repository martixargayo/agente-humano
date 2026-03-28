from __future__ import annotations

import os

from evaluacion.engine.communication_activation_policy import get_communication_activation_policy
from evaluacion.engine.communication_llm_models import get_visual_llm_model

COMM_VISUAL_MAX_FRAMES = 90
COMM_VISUAL_BATCH_TARGET = 30
COMM_VISUAL_TAIL_MIN = 6
COMM_VISUAL_DETAIL = 'low'

COMM_VISUAL_OPENAI_TIMEOUT_S_DEFAULT = 25.0
COMM_VISUAL_OPENAI_MAX_RETRIES_DEFAULT = 2


def get_visual_mode() -> str:
    return get_communication_activation_policy().visual_mode


def is_visual_llm_enabled() -> bool:
    return get_visual_mode() == 'llm_v1'


def get_visual_openai_model() -> str:
    return get_visual_llm_model()


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
