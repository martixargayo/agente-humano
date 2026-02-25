from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any


_LIVETRACE2_RING: deque[dict[str, Any]] = deque(maxlen=300)


def build_livetrace2_event(
    *,
    user_id: str,
    session_id: str,
    session: Any,
    trace_index: int,
    trace_item: dict,
) -> dict:
    base = dict(trace_item or {}) if isinstance(trace_item, dict) else {}
    turn_count = 0
    if session is not None:
        turn_count = int(getattr(session, "turn_count", 0) or 0)
    event = {
        "user_id": str(user_id or ""),
        "session_id": str(session_id or ""),
        "trace_index": int(trace_index or 0),
        "turn_count": turn_count,
        "kind": str(base.get("kind") or "trace"),
        "payload": base,
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    return event


def append_livetrace2_event(event: dict[str, Any]) -> None:
    if isinstance(event, dict):
        _LIVETRACE2_RING.append(dict(event))


def list_recent_livetrace2_events(limit: int = 10) -> list[dict]:
    safe_limit = max(0, int(limit or 0))
    if safe_limit == 0:
        return []
    return list(_LIVETRACE2_RING)[-safe_limit:]
