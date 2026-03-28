from __future__ import annotations

import os
from typing import Any

from evaluacion.engine.communication_activation_policy import (
    get_communication_activation_policy,
    is_force_safe_mode_enabled,
)
from evaluacion.engine.communication_llm_config import parse_env_bool

_COMM_DEBUG_FLAG = 'COMM_DEBUG_FLAGS_ENABLED'


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
    policy = get_communication_activation_policy()
    runtime_fingerprint = {
        'git_sha': _resolve_git_sha(),
        'railway_service_name': _read_raw_env_value('RAILWAY_SERVICE_NAME'),
        'railway_environment_name': _read_raw_env_value('RAILWAY_ENVIRONMENT_NAME'),
        'hostname': _read_raw_env_value('HOSTNAME'),
        'pid': str(os.getpid()),
    }
    return {
        'policy_source': policy.policy_source,
        'policy_version': policy.policy_version,
        'effective_policy': policy.to_dict(),
        'safety_controls': {
            'force_safe_mode': is_force_safe_mode_enabled(),
        },
        'openai': {
            'has_openai_api_key': bool((os.getenv('OPENAI_API_KEY') or '').strip()),
        },
        'runtime_fingerprint': runtime_fingerprint,
    }
