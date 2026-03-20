from __future__ import annotations

import logging
import os
import threading
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

SESSION_LOCK_KEY_PREFIX = "session-lock"


class SessionBusyError(RuntimeError):
    def __init__(self, *, user_id: str, session_id: str, retry_after_seconds: int, lock_backend: str) -> None:
        super().__init__("session_busy")
        self.user_id = user_id
        self.session_id = session_id
        self.retry_after_seconds = retry_after_seconds
        self.lock_backend = lock_backend


class RedisLockClientProtocol(Protocol):
    def set(self, key: str, value: str, *, nx: bool | None = None, ex: int | None = None) -> Any: ...

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...


def _lock_ttl_seconds() -> int:
    return max(15, int(os.getenv("SESSION_EXECUTION_LOCK_TTL_SECONDS", "180")))


def _lock_refresh_seconds() -> int:
    ttl = _lock_ttl_seconds()
    configured = int(os.getenv("SESSION_EXECUTION_LOCK_REFRESH_SECONDS", "30"))
    return max(5, min(configured, max(5, ttl - 5)))


def _retry_after_seconds() -> int:
    return max(1, int(os.getenv("SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS", "2")))


def session_lock_key(*, user_id: str, session_id: str, key_prefix: str = SESSION_LOCK_KEY_PREFIX) -> str:
    return f"{key_prefix}:{user_id}:{session_id}"


@dataclass
class SessionExecutionLease(AbstractContextManager["SessionExecutionLease"]):
    user_id: str
    session_id: str
    release_callback: Callable[[], None]

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release_callback()
        return None


class InMemorySessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def acquire(self, *, user_id: str, session_id: str) -> SessionExecutionLease:
        key = session_lock_key(user_id=user_id, session_id=session_id)
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            logger.warning("session_lock_busy backend=memory key=%s", key)
            raise SessionBusyError(
                user_id=user_id,
                session_id=session_id,
                retry_after_seconds=_retry_after_seconds(),
                lock_backend="memory",
            )
        logger.info("session_lock_acquired backend=memory key=%s", key)

        released = False

        def _release() -> None:
            nonlocal released
            if released:
                return
            released = True
            lock.release()
            logger.info("session_lock_released backend=memory key=%s", key)

        return SessionExecutionLease(user_id=user_id, session_id=session_id, release_callback=_release)


class RedisSessionLockManager:
    _REFRESH_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
end
return 0
"""
    _RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

    def __init__(
        self,
        client: RedisLockClientProtocol,
        *,
        key_prefix: str = SESSION_LOCK_KEY_PREFIX,
        ttl_seconds: int | None = None,
        refresh_seconds: int | None = None,
    ) -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds or _lock_ttl_seconds()
        self._refresh_seconds = refresh_seconds or _lock_refresh_seconds()

    def acquire(self, *, user_id: str, session_id: str) -> SessionExecutionLease:
        key = session_lock_key(user_id=user_id, session_id=session_id, key_prefix=self._key_prefix)
        token = uuid.uuid4().hex
        acquired = self._client.set(key, token, nx=True, ex=self._ttl_seconds)
        if not acquired:
            logger.warning("session_lock_busy backend=redis key=%s ttl=%s", key, self._ttl_seconds)
            raise SessionBusyError(
                user_id=user_id,
                session_id=session_id,
                retry_after_seconds=_retry_after_seconds(),
                lock_backend="redis",
            )

        stop_event = threading.Event()
        refresh_lost = threading.Event()
        refresh_thread: threading.Thread | None = None

        if self._refresh_seconds > 0 and self._ttl_seconds > self._refresh_seconds:
            refresh_thread = threading.Thread(
                target=self._heartbeat,
                args=(key, token, stop_event, refresh_lost),
                daemon=True,
                name=f"session-lock:{session_id}",
            )
            refresh_thread.start()

        logger.info(
            "session_lock_acquired backend=redis key=%s ttl=%s refresh=%s",
            key,
            self._ttl_seconds,
            self._refresh_seconds,
        )

        released = False

        def _release() -> None:
            nonlocal released
            if released:
                return
            released = True
            stop_event.set()
            if refresh_thread is not None:
                refresh_thread.join(timeout=1.0)
            deleted = self._client.eval(self._RELEASE_SCRIPT, 1, key, token)
            logger.info(
                "session_lock_released backend=redis key=%s deleted=%s refresh_lost=%s",
                key,
                bool(deleted),
                refresh_lost.is_set(),
            )

        return SessionExecutionLease(user_id=user_id, session_id=session_id, release_callback=_release)

    def _heartbeat(self, key: str, token: str, stop_event: threading.Event, refresh_lost: threading.Event) -> None:
        while not stop_event.wait(self._refresh_seconds):
            try:
                refreshed = self._client.eval(self._REFRESH_SCRIPT, 1, key, token, self._ttl_seconds)
            except Exception as exc:  # pragma: no cover - defensive runtime logging
                logger.warning("session_lock_refresh_error key=%s error=%s", key, exc)
                continue
            if not refreshed:
                refresh_lost.set()
                logger.warning("session_lock_refresh_lost_ownership key=%s", key)
                return
            logger.info("session_lock_refreshed key=%s ttl=%s", key, self._ttl_seconds)


_IN_MEMORY_SESSION_LOCK_MANAGER = InMemorySessionLockManager()
_REDIS_LOCK_MANAGERS: dict[int, RedisSessionLockManager] = {}


def get_session_lock_manager():
    from sessions.state import get_session_store

    store = get_session_store()
    client = getattr(store, "client", None)
    if client is None:
        logger.info("session_lock_manager_selected backend=memory")
        return _IN_MEMORY_SESSION_LOCK_MANAGER

    manager = _REDIS_LOCK_MANAGERS.get(id(client))
    if manager is None:
        manager = RedisSessionLockManager(client)
        _REDIS_LOCK_MANAGERS[id(client)] = manager
    logger.info("session_lock_manager_selected backend=redis")
    return manager


def acquire_session_execution_lock(*, user_id: str, session_id: str) -> SessionExecutionLease:
    return get_session_lock_manager().acquire(user_id=user_id, session_id=session_id)
