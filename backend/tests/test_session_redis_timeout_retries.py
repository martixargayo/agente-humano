from __future__ import annotations

from sessions.redis_store import RedisSessionStore
from sessions.session_lock import RedisSessionLockManager
from sessions.state import SessionState


class _FlakyRedisStoreClient:
    def __init__(self) -> None:
        self.fail_get = 2
        self.fail_set = 2
        self.fail_expire = 2
        self.data: dict[str, str] = {}

    def get(self, key: str):
        if self.fail_get > 0:
            self.fail_get -= 1
            raise RuntimeError("Timeout writing to socket")
        return self.data.get(key)

    def set(self, key: str, value: str):
        if self.fail_set > 0:
            self.fail_set -= 1
            raise RuntimeError("Timeout writing to socket")
        self.data[key] = value
        return True

    def delete(self, key: str):
        self.data.pop(key, None)
        return 1

    def expire(self, key: str, seconds: int):
        if self.fail_expire > 0:
            self.fail_expire -= 1
            raise RuntimeError("Timeout writing to socket")
        return True

    def scan_iter(self, match: str):
        return []


class _FlakyRedisLockClient:
    def __init__(self) -> None:
        self.fail_set = 2
        self.fail_eval = 2
        self.lock_value: str | None = None

    def set(self, key: str, value: str, *, nx: bool | None = None, ex: int | None = None):
        _ = (key, nx, ex)
        if self.fail_set > 0:
            self.fail_set -= 1
            raise RuntimeError("Timeout writing to socket")
        self.lock_value = value
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args):
        _ = (script, numkeys, keys_and_args)
        if self.fail_eval > 0:
            self.fail_eval -= 1
            raise RuntimeError("Timeout writing to socket")
        return 1


def test_redis_session_store_retries_transient_socket_timeout(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_REDIS_TIMEOUT_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("SESSION_REDIS_TIMEOUT_RETRY_BACKOFF_SECONDS", "0")
    client = _FlakyRedisStoreClient()
    store = RedisSessionStore(client)

    state = SessionState(user_id="u", session_id="s")
    store.save(state)
    loaded = store.get(user_id="u", session_id="s")
    assert loaded is not None

    store.touch(user_id="u", session_id="s", ttl_seconds=10)


def test_redis_session_lock_retries_transient_socket_timeout(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_REDIS_TIMEOUT_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("SESSION_REDIS_TIMEOUT_RETRY_BACKOFF_SECONDS", "0")
    client = _FlakyRedisLockClient()
    manager = RedisSessionLockManager(client, ttl_seconds=30, refresh_seconds=0)

    lease = manager.acquire(user_id="u", session_id="s")
    lease.__exit__(None, None, None)
