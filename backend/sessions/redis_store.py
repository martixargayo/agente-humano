from __future__ import annotations

from typing import Any, Iterable, Protocol

try:
    from redis import Redis
except Exception:  # pragma: no cover - dependency can be absent in local envs using memory store
    Redis = None  # type: ignore[assignment]

from .state import SessionEnvelope, SessionState, export_session_envelope, hydrate_session_state

SESSION_KEY_PREFIX = "session"


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

    def _session_key(self, *, user_id: str, session_id: str) -> str:
        return f"{self._key_prefix}:{user_id}:{session_id}"

    def get(self, *, user_id: str, session_id: str) -> SessionState | None:
        raw = self._client.get(self._session_key(user_id=user_id, session_id=session_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        envelope = SessionEnvelope.model_validate_json(raw)
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
        self._client.set(self._session_key(user_id=state.user_id, session_id=state.session_id), envelope.model_dump_json())

    def delete(self, *, user_id: str, session_id: str) -> None:
        self._client.delete(self._session_key(user_id=user_id, session_id=session_id))

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
        self._client.expire(self._session_key(user_id=user_id, session_id=session_id), ttl_seconds)


def build_redis_client_from_url(redis_url: str):
    if Redis is None:
        raise RuntimeError("redis_dependency_missing")
    return Redis.from_url(redis_url, decode_responses=False)
