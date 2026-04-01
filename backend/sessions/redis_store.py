from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterable, Protocol

try:
    from redis import Redis
except Exception:  # pragma: no cover - dependency can be absent in local envs using memory store
    Redis = None  # type: ignore[assignment]

from .state import SessionEnvelope, SessionState, export_session_envelope, hydrate_session_state

SESSION_KEY_PREFIX = "session"
logger = logging.getLogger(__name__)


def _is_redis_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "timeout" in text and "socket" in text


def _redis_timeout_retry_attempts() -> int:
    return max(1, int(os.getenv("SESSION_REDIS_TIMEOUT_RETRY_ATTEMPTS", "6")))


def _redis_timeout_retry_backoff_seconds() -> float:
    return max(0.0, float(os.getenv("SESSION_REDIS_TIMEOUT_RETRY_BACKOFF_SECONDS", "0.25")))


def _with_redis_timeout_retries(operation: str, fn):
    attempts = _redis_timeout_retry_attempts()
    backoff = _redis_timeout_retry_backoff_seconds()
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not _is_redis_timeout_error(exc) or attempt >= attempts:
                if _is_redis_timeout_error(exc):
                    logger.error(
                        "redis_operation_timeout_exhausted operation=%s attempts=%s error=%s",
                        operation,
                        attempt,
                        exc,
                    )
                raise
            logger.warning(
                "redis_operation_timeout_retry operation=%s attempt=%s/%s error=%s",
                operation,
                attempt,
                attempts,
                exc,
            )
            if backoff > 0:
                time.sleep(backoff * attempt)


class RedisClientProtocol(Protocol):
    def get(self, key: str) -> bytes | str | None: ...

    def set(self, key: str, value: str) -> Any: ...

    def delete(self, key: str) -> Any: ...

    def expire(self, key: str, seconds: int) -> Any: ...

    def scan_iter(self, match: str) -> Iterable[bytes | str]: ...


class RedisSessionStore:
    def __init__(self, client: RedisClientProtocol, *, key_prefix: str = SESSION_KEY_PREFIX) -> None:
        self._client = client
        self._key_prefix = key_prefix.strip() or SESSION_KEY_PREFIX

    @property
    def client(self) -> RedisClientProtocol:
        return self._client

    def _session_key(self, *, user_id: str, session_id: str) -> str:
        return f"{self._key_prefix}:{user_id}:{session_id}"

    def get(self, *, user_id: str, session_id: str) -> SessionState | None:
        session_key = self._session_key(user_id=user_id, session_id=session_id)
        raw = _with_redis_timeout_retries("get", lambda: self._client.get(session_key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            envelope = SessionEnvelope.model_validate_json(raw)
        except Exception as exc:
            logger.error("redis_session_envelope_decode_error key=%s error=%s", session_key, exc)
            raise
        return hydrate_session_state(envelope)

    def get_or_create(self, *, user_id: str, session_id: str) -> SessionState:
        existing = self.get(user_id=user_id, session_id=session_id)
        if existing is not None:
            return existing
        state = SessionState(user_id=user_id, session_id=session_id)
        self.save(state)
        return state

    def save(self, state: SessionState) -> None:
        envelope = export_session_envelope(state)
        _with_redis_timeout_retries(
            "set",
            lambda: self._client.set(
                self._session_key(user_id=state.user_id, session_id=state.session_id),
                envelope.model_dump_json(),
            ),
        )

    def delete(self, *, user_id: str, session_id: str) -> None:
        _with_redis_timeout_retries("delete", lambda: self._client.delete(self._session_key(user_id=user_id, session_id=session_id)))

    def clear(self) -> None:
        for key in list(self._client.scan_iter(match=f"{self._key_prefix}:*")):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            self._client.delete(key)

    def iter_entries(self) -> Iterable[tuple[str, str, SessionState]]:
        prefix = f"{self._key_prefix}:"
        for raw_key in self._client.scan_iter(match=f"{self._key_prefix}:*"):
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            try:
                _, user_id, session_id = key.split(":", 2)
            except ValueError:
                if not key.startswith(prefix):
                    continue
                continue
            state = self.get(user_id=user_id, session_id=session_id)
            if state is not None:
                yield user_id, session_id, state

    def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        _with_redis_timeout_retries(
            "expire",
            lambda: self._client.expire(self._session_key(user_id=user_id, session_id=session_id), ttl_seconds),
        )


def build_redis_client_from_url(redis_url: str):
    if Redis is None:
        raise RuntimeError("redis_dependency_missing")
    connect_timeout = float(os.getenv("SESSION_REDIS_CONNECT_TIMEOUT_SECONDS", "2"))
    socket_timeout = float(os.getenv("SESSION_REDIS_SOCKET_TIMEOUT_SECONDS", "2"))
    health_check_interval = int(os.getenv("SESSION_REDIS_HEALTH_CHECK_INTERVAL_SECONDS", "30"))

    logger.info(
        "Configuring Redis session client with connect_timeout=%ss socket_timeout=%ss health_check_interval=%ss",
        connect_timeout,
        socket_timeout,
        health_check_interval,
    )

    return Redis.from_url(
        redis_url,
        decode_responses=False,
        socket_connect_timeout=connect_timeout,
        socket_timeout=socket_timeout,
        health_check_interval=health_check_interval,
        retry_on_timeout=False,
    )
