from __future__ import annotations

import hashlib
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ProviderCallEvent:
    event_type: str
    call_subtype: str
    node_name: str | None
    model: str | None
    started_at: str
    finished_at: str
    latency_ms: int
    payload_chars: int
    payload_hash: str
    request_context_mode: str | None
    request_context_has_conversation_id: bool
    request_context_has_previous_response_id: bool
    error: str | None = None


@dataclass
class TurnProbe:
    logical_user_message_id: str | None
    logical_attempt_index: int | None
    client_request_id: str | None
    backend_turn_attempt_id: str | None
    turn_id: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_calls: list[ProviderCallEvent] = field(default_factory=list)
    side_effect_hooks: list[dict[str, Any]] = field(default_factory=list)


_ACTIVE: ContextVar[TurnProbe | None] = ContextVar("forensics_turn_probe", default=None)


def begin_turn_probe(*, logical_user_message_id: str | None, logical_attempt_index: int | None, client_request_id: str | None, backend_turn_attempt_id: str | None) -> object:
    probe = TurnProbe(
        logical_user_message_id=logical_user_message_id,
        logical_attempt_index=logical_attempt_index,
        client_request_id=client_request_id,
        backend_turn_attempt_id=backend_turn_attempt_id,
    )
    return _ACTIVE.set(probe)


def end_turn_probe(token: object) -> TurnProbe | None:
    probe = _ACTIVE.get()
    _ACTIVE.reset(token)
    return probe


def get_turn_probe() -> TurnProbe | None:
    return _ACTIVE.get()


def set_turn_id(turn_id: str) -> None:
    probe = _ACTIVE.get()
    if probe is not None:
        probe.turn_id = turn_id


def _mode_from_request_context(request_context: dict[str, str] | None) -> str | None:
    if not isinstance(request_context, dict):
        return None
    if request_context.get("conversation"):
        return "conversation"
    if request_context.get("previous_response_id"):
        return "previous_response_id"
    return "stateless"


def _serialize_payload(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(payload)


def record_provider_call(*, call_subtype: str, node_name: str | None, model: str | None, payload: Any, request_context: dict[str, str] | None, fn: Any) -> Any:
    probe = _ACTIVE.get()
    started_perf = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    payload_serialized = _serialize_payload(payload)
    payload_hash = hashlib.sha256(payload_serialized.encode("utf-8")).hexdigest()[:16]
    error: str | None = None
    try:
        return fn()
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        finished_at = datetime.now(timezone.utc).isoformat()
        latency_ms = int((time.perf_counter() - started_perf) * 1000)
        if probe is not None:
            probe.provider_calls.append(
                ProviderCallEvent(
                    event_type="provider_call",
                    call_subtype=call_subtype,
                    node_name=node_name,
                    model=model,
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=latency_ms,
                    payload_chars=len(payload_serialized),
                    payload_hash=payload_hash,
                    request_context_mode=_mode_from_request_context(request_context),
                    request_context_has_conversation_id=bool((request_context or {}).get("conversation")),
                    request_context_has_previous_response_id=bool((request_context or {}).get("previous_response_id")),
                    error=error,
                )
            )


def record_side_effect_hook(*, hook_name: str, payload: dict[str, Any], error: str | None = None) -> None:
    probe = _ACTIVE.get()
    if probe is None:
        return
    serialized = _serialize_payload(payload)
    probe.side_effect_hooks.append(
        {
            "event_type": "side_effect_hook",
            "hook_name": hook_name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "payload_chars": len(serialized),
            "payload_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16],
            "error": error,
            "payload": payload,
        }
    )
