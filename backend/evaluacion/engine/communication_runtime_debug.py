from __future__ import annotations

import os
from typing import Any

from evaluacion.engine.communication_llm_config import parse_env_bool, parse_env_choice

_COMM_DEBUG_FLAG = 'COMM_DEBUG_FLAGS_ENABLED'
_VISUAL_MODE_DEFAULT = 'metadata'

_RAW_DEBUG_ENV_KEYS = (
    'COMM_CONTENT_OPENAI_ENABLED',
    'COMM_AUDIO_OPENAI_ENABLED',
    'COMM_SYNTHESIS_OPENAI_ENABLED',
    'COMM_VISUAL_MODE',
    'COMM_VISUAL_OPENAI_ENABLED',
)


def is_comm_debug_flags_enabled() -> bool:
    return parse_env_bool(_COMM_DEBUG_FLAG, default=False)


def _read_raw_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else ''


def _resolve_git_sha() -> str | None:
    for key in ('GIT_SHA', 'RAILWAY_GIT_COMMIT_SHA', 'SOURCE_VERSION'):
        value = _read_raw_env_value(key)
        if value:
            return value
    return None


def build_communication_llm_flags_snapshot() -> dict[str, Any]:
    raw_env = {name: _read_raw_env_value(name) for name in _RAW_DEBUG_ENV_KEYS}
    parsed_env = {
        'content_llm_enabled': parse_env_bool('COMM_CONTENT_OPENAI_ENABLED', default=False),
        'audio_llm_enabled': parse_env_bool('COMM_AUDIO_OPENAI_ENABLED', default=False),
        'global_synthesis_llm_enabled': parse_env_bool('COMM_SYNTHESIS_OPENAI_ENABLED', default=False),
        'visual_mode': parse_env_choice('COMM_VISUAL_MODE', allowed={'metadata', 'llm_v1'}, default=_VISUAL_MODE_DEFAULT),
        'visual_llm_enabled': parse_env_bool('COMM_VISUAL_OPENAI_ENABLED', default=False),
    }
    runtime_fingerprint = {
        'git_sha': _resolve_git_sha(),
        'railway_service_name': _read_raw_env_value('RAILWAY_SERVICE_NAME'),
        'railway_environment_name': _read_raw_env_value('RAILWAY_ENVIRONMENT_NAME'),
        'hostname': _read_raw_env_value('HOSTNAME'),
        'pid': str(os.getpid()),
    }
    return {
        'raw_env': raw_env,
        'parsed_env': parsed_env,
        'openai': {
            'has_openai_api_key': bool((os.getenv('OPENAI_API_KEY') or '').strip()),
        },
        'runtime_fingerprint': runtime_fingerprint,
    }
