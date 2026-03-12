from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

from sessions.state import SESSIONS, SessionState

PREFERRED_TRACE_KEYS = ["negotiation_canonical_traces"]


def iter_session_entries() -> Iterable[tuple[str, str, SessionState]]:
    for (user_id, session_id), state in SESSIONS.items():
        yield user_id, session_id, state


def get_state(user_id: str, session_id: str) -> SessionState | None:
    return SESSIONS.get((user_id, session_id))


def session_key(user_id: str, session_id: str) -> str:
    return f"{user_id}::{session_id}"


def parse_session_key(value: str) -> tuple[str, str]:
    if "::" not in value:
        raise ValueError("session_key inválida")
    user_id, session_id = value.split("::", 1)
    if not user_id or not session_id:
        raise ValueError("session_key inválida")
    return user_id, session_id


def resolve_traces(state: SessionState, memory_key: str | None = None) -> list[dict[str, Any]]:
    if memory_key:
        candidate = state.world_state.get(f"{memory_key}_traces")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    for key in PREFERRED_TRACE_KEYS:
        candidate = state.world_state.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    fallback_keys = sorted(
        key for key, value in state.world_state.items() if key.endswith("_traces") and isinstance(value, list)
    )
    for key in fallback_keys:
        value = state.world_state.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


ACTIVE_CHAT_BINDING_PATH = Path(__file__).resolve().parent / "active_chat_binding.json"


def read_active_chat_binding() -> dict[str, Any]:
    if not ACTIVE_CHAT_BINDING_PATH.exists():
        return {}
    raw = ACTIVE_CHAT_BINDING_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def write_active_chat_binding(payload: dict[str, Any]) -> None:
    tmp = ACTIVE_CHAT_BINDING_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ACTIVE_CHAT_BINDING_PATH)
