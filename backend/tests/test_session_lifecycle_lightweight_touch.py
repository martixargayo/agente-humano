from __future__ import annotations

from sessions.lifecycle import touch_existing_session_if_present
from sessions.state import SessionState, reset_session_store, set_session_store


class _CountingStore:
    def __init__(self) -> None:
        self.touch_calls = 0
        self.get_calls = 0
        self.saved: dict[tuple[str, str], SessionState] = {}

    def get(self, *, user_id: str, session_id: str):
        self.get_calls += 1
        return self.saved.get((user_id, session_id))

    def get_or_create(self, *, user_id: str, session_id: str):
        state = self.saved.get((user_id, session_id))
        if state is None:
            state = SessionState(user_id=user_id, session_id=session_id)
            self.saved[(user_id, session_id)] = state
        return state

    def save(self, state: SessionState) -> None:
        self.saved[(state.user_id, state.session_id)] = state

    def delete(self, *, user_id: str, session_id: str) -> None:
        self.saved.pop((user_id, session_id), None)

    def clear(self) -> None:
        self.saved.clear()

    def iter_entries(self):
        for (u, s), st in self.saved.items():
            yield u, s, st

    def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None:
        _ = (user_id, session_id, ttl_seconds)
        self.touch_calls += 1


class _TimeoutTouchStore(_CountingStore):
    def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None:
        _ = (user_id, session_id, ttl_seconds)
        self.touch_calls += 1
        raise RuntimeError("Timeout writing to socket")


def test_touch_existing_session_prefers_lightweight_touch_without_get_roundtrip() -> None:
    store = _CountingStore()
    set_session_store(store)
    try:
        ttl = touch_existing_session_if_present(
            user_id="u_life",
            session_id="s_life",
            scope="active",
            reason="unit_test",
        )
        assert ttl is not None
        assert store.touch_calls == 1
        assert store.get_calls == 0
    finally:
        reset_session_store()


def test_touch_existing_session_does_not_fallback_to_heavy_path_on_socket_timeout() -> None:
    store = _TimeoutTouchStore()
    set_session_store(store)
    try:
        try:
            touch_existing_session_if_present(
                user_id="u_life",
                session_id="s_life",
                scope="active",
                reason="unit_test_timeout",
            )
            raise AssertionError("expected timeout")
        except RuntimeError as exc:
            assert "Timeout writing to socket" in str(exc)
        assert store.touch_calls == 1
        assert store.get_calls == 0
    finally:
        reset_session_store()
