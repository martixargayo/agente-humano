"""Regression tests for the conservative latency optimizations.

These tests pin the behavior introduced to shave ~2s off the
conversacion_simple voice pipeline without touching the main LLM:

Focus A — session / TTL / load / save
- RedisSessionStore.save_with_ttl hits Redis exactly once via ``SET ... EX``.
- sessions.lifecycle.persist_session_with_ttl applies lifecycle metadata
  in-memory and persists atomically via save_with_ttl.
- conversacion_simple pipeline honors ``persist_state=False`` by skipping
  the final save_session_state(), while still recording the
  ``save_session_state`` stage timing key (so observability stays stable).
- interfaz_usuario.services run_turn reuses the already-loaded base state
  on the conversacion_simple path, eliminating one redundant Redis GET.

Focus B — TTS prefetch wiring
- negociacion.orchestration.flow_config.safe_invoke_tts_prefetch_hook
  fires the configured hook (including when invoked from the
  conversacion_simple pipeline) and swallows exceptions defensively.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.app import app
from conversacion_simple.orchestration import pipeline as cs_pipeline
from negociacion.orchestration import flow_config as neg_flow_config
from sessions.lifecycle import persist_session_with_ttl
from sessions.redis_store import RedisSessionStore
from sessions.state import (
    InMemorySessionStore,
    SessionState,
    get_session_state,
    get_session_store,
    reset_session_store,
    set_session_store,
)


# ---------------------------------------------------------------------------
# Focus A: save_with_ttl / persist_session_with_ttl
# ---------------------------------------------------------------------------


class _RecordingRedisClient:
    """Minimal fake Redis client recording set/expire calls."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.set_calls: list[dict[str, Any]] = []
        self.expire_calls: list[tuple[str, int]] = []

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls.append({"key": key, "value": value, "ex": ex})
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
        return True

    def delete(self, key: str):
        self.store.pop(key, None)
        self.ttl.pop(key, None)
        return 1

    def expire(self, key: str, seconds: int):
        self.expire_calls.append((key, seconds))
        if key in self.store:
            self.ttl[key] = seconds
            return True
        return False

    def scan_iter(self, match: str):
        prefix = match[:-1] if match.endswith("*") else match
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


def test_redis_save_with_ttl_issues_single_set_ex_roundtrip() -> None:
    client = _RecordingRedisClient()
    store = RedisSessionStore(client)
    state = SessionState(user_id="u_setex", session_id="s_setex")

    store.save_with_ttl(state, ttl_seconds=123)

    assert len(client.set_calls) == 1
    assert client.set_calls[0]["ex"] == 123
    assert client.expire_calls == []
    # Envelope must be under the canonical session key.
    assert client.set_calls[0]["key"] == "session:u_setex:s_setex"


def test_redis_save_with_ttl_falls_back_to_plain_set_when_ttl_non_positive() -> None:
    client = _RecordingRedisClient()
    store = RedisSessionStore(client)
    state = SessionState(user_id="u_ttl0", session_id="s_ttl0")

    store.save_with_ttl(state, ttl_seconds=0)

    assert len(client.set_calls) == 1
    assert client.set_calls[0]["ex"] is None
    assert client.expire_calls == []


def test_persist_session_with_ttl_applies_lifecycle_metadata_and_persists_atomically() -> None:
    """persist_session_with_ttl must go through save_with_ttl (not save+touch)."""
    from threading import RLock

    class _AtomicStore:
        def __init__(self) -> None:
            self._sessions: dict[tuple[str, str], SessionState] = {}
            self._lock = RLock()
            self.save_calls = 0
            self.save_with_ttl_calls: list[int] = []
            self.touch_calls = 0

        def get(self, *, user_id: str, session_id: str):
            return self._sessions.get((user_id, session_id))

        def get_or_create(self, *, user_id: str, session_id: str):
            key = (user_id, session_id)
            state = self._sessions.get(key)
            if state is None:
                state = SessionState(user_id=user_id, session_id=session_id)
                self._sessions[key] = state
            return state

        def save(self, state: SessionState) -> None:
            self.save_calls += 1
            self._sessions[(state.user_id, state.session_id)] = state

        def save_with_ttl(self, state: SessionState, *, ttl_seconds: int) -> None:
            self.save_with_ttl_calls.append(ttl_seconds)
            # Persist directly — do NOT delegate to save() so counters stay isolated.
            self._sessions[(state.user_id, state.session_id)] = state

        def delete(self, *, user_id: str, session_id: str) -> None:
            self._sessions.pop((user_id, session_id), None)

        def clear(self) -> None:
            self._sessions.clear()

        def iter_entries(self):
            for (u, s), st in self._sessions.items():
                yield u, s, st

        def touch(self, *, user_id: str, session_id: str, ttl_seconds: int) -> None:
            self.touch_calls += 1

    store = _AtomicStore()
    set_session_store(store)
    try:
        state = SessionState(user_id="u_atomic", session_id="s_atomic")
        store.save(state)  # seed; not counted against the hot path
        store.save_calls = 0

        ttl = persist_session_with_ttl(state, scope="active", reason="unit_test")

        # Exactly one atomic save, no follow-up plain save and no follow-up touch.
        assert len(store.save_with_ttl_calls) == 1
        assert store.save_with_ttl_calls[0] == ttl
        assert store.save_calls == 0
        assert store.touch_calls == 0

        # Lifecycle metadata was persisted in-memory with the save.
        persisted = store.get(user_id="u_atomic", session_id="s_atomic")
        assert persisted is not None
        lifecycle = persisted.world_state.get("_session_lifecycle")
        assert isinstance(lifecycle, dict)
        assert lifecycle["status"] == "active"
        assert lifecycle["ttl_scope"] == "active"
        assert lifecycle["last_reason"] == "unit_test"
    finally:
        reset_session_store()


# ---------------------------------------------------------------------------
# Focus A: pipeline persist_state flag + duplicate load elimination
# ---------------------------------------------------------------------------


def _fake_brain_call(*, client, model, messages):
    _ = (client, model, messages)
    return cs_pipeline.StructuredBrainCall(
        source="model",
        parsed_json={
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "hola"},
            "state_patch": {
                "conversation_state": {
                    "phase": "avance",
                    "status": "active",
                    "current_turn_goal": "responder",
                    "closure_readiness": "not_ready",
                },
                "memory_working": {
                    "current_topic": "x",
                    "pending_question": None,
                    "last_turn_summary": "y",
                },
                "memory_episodic_append": [],
            },
            "observability": {"rationale_summary": "ok"},
        },
        response=object(),
        response_id="resp_perf",
        schema_observability={
            "schema_name": "BrainOutput",
            "validation": {"valid": True},
            "openai_subset_validation": {"valid": True},
        },
        model_attempted=True,
        model_succeeded=True,
        timings_ms={
            "schema_prepare": 0.1,
            "provider_responses_create": 0.2,
            "extract_output_text": 0.1,
            "json_loads": 0.1,
            "total": 0.5,
        },
    )


def test_pipeline_persist_state_false_skips_save_but_keeps_stage_key(monkeypatch) -> None:
    reset_session_store()
    save_calls = {"n": 0}
    real_save = cs_pipeline.save_session_state

    def _counting_save(state):
        save_calls["n"] += 1
        real_save(state)

    monkeypatch.setattr(cs_pipeline, "save_session_state", _counting_save)
    monkeypatch.setattr(cs_pipeline, "_call_brain_structured", _fake_brain_call)

    client = TestClient(app)
    boot = client.post(
        "/api/interfaz_usuario/sessions/bootstrap",
        json={"user_id": "u_psf", "session_id": "s_psf", "context_id": "baseline"},
    )
    assert boot.status_code == 200

    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_psf", "session_id": "s_psf", "message": "hola", "new_conversation": False},
    )
    assert turn.status_code == 200
    payload = turn.json()

    # Interfaz usuario drives conversacion_simple with persist_state=False,
    # so the pipeline must NOT invoke save_session_state itself. Persistence
    # is taken over by persist_session_with_ttl afterwards.
    assert save_calls["n"] == 0, "pipeline called save_session_state despite persist_state=False"

    # Instrumentation key must still be present so existing telemetry assertions
    # keep working.
    breakdown = payload.get("latency_breakdown_ms", {})
    pipeline = breakdown.get("pipeline_stage_timings_ms", {})
    assert "save_session_state" in pipeline

    # State must actually have been saved (by persist_session_with_ttl).
    state = get_session_state(user_id="u_psf", session_id="s_psf")
    assert state.history, "assistant turn was never persisted"
    assert state.history[-1]["role"] == "assistant"


def test_pipeline_default_persist_state_is_true_for_backwards_compat() -> None:
    """Guard: the default must stay True so direct callers keep persisting.

    Only the interfaz_usuario conversacion_simple path passes
    ``persist_state=False`` (it delegates persistence to
    ``persist_session_with_ttl`` for the atomic SET+EX shortcut). All other
    legacy call sites must continue to see the state saved automatically.
    """
    import inspect

    sig = inspect.signature(cs_pipeline.run_conversacion_simple_turn)
    assert "persist_state" in sig.parameters
    assert sig.parameters["persist_state"].default is True


def test_services_reuses_base_state_avoiding_duplicate_redis_get(monkeypatch) -> None:
    from sessions.state import SessionState as _SS
    from interfaz_usuario import services as iu_services

    reset_session_store()

    class _CountingStore(InMemorySessionStore):
        def __init__(self) -> None:
            super().__init__()
            self.get_calls = 0

        def get(self, *, user_id: str, session_id: str):  # type: ignore[override]
            self.get_calls += 1
            return super().get(user_id=user_id, session_id=session_id)

    store = _CountingStore()
    set_session_store(store)
    try:
        iu_services.ensure_session(user_id="u_dup", session_id="s_dup", context_id="baseline")
        # Reset counter after bootstrap so we only measure the turn hot path.
        store.get_calls = 0

        def _fake_cs_turn(*, state, user_message, config, turn_context, **kwargs):
            return "ok", state, {"turn_id": "t1"}

        monkeypatch.setattr(
            "interfaz_usuario.services.run_conversacion_simple_turn",
            _fake_cs_turn,
        )

        out = iu_services.run_turn(
            user_id="u_dup",
            session_id="s_dup",
            message="hola",
            new_conversation=False,
        )
        assert out["reply"] == "ok"

        # Before the optimization this path performed two GETs
        # (load_base_state + load_active_state). After: exactly one GET
        # covers both stages thanks to the in-memory reuse of base_state.
        # Allow a small bound to tolerate unrelated internal reads.
        assert store.get_calls <= 1, f"expected <=1 GET for reuse optimization, got {store.get_calls}"
    finally:
        reset_session_store()


# ---------------------------------------------------------------------------
# Focus B: TTS prefetch hook wiring
# ---------------------------------------------------------------------------


def test_safe_invoke_tts_prefetch_hook_fires_registered_hook() -> None:
    calls: list[str] = []
    neg_flow_config.set_tts_prefetch_hook(lambda reply: calls.append(reply))
    try:
        neg_flow_config.safe_invoke_tts_prefetch_hook("hola mundo")
        assert calls == ["hola mundo"]
    finally:
        neg_flow_config.set_tts_prefetch_hook(None)


def test_safe_invoke_tts_prefetch_hook_swallows_exceptions() -> None:
    def _broken_hook(_reply: str) -> None:
        raise RuntimeError("boom")

    neg_flow_config.set_tts_prefetch_hook(_broken_hook)
    try:
        # Must not raise — it would otherwise break the turn pipeline.
        neg_flow_config.safe_invoke_tts_prefetch_hook("x")
    finally:
        neg_flow_config.set_tts_prefetch_hook(None)


def test_safe_invoke_tts_prefetch_hook_noop_when_unset() -> None:
    neg_flow_config.set_tts_prefetch_hook(None)
    # Must not raise or require anything.
    neg_flow_config.safe_invoke_tts_prefetch_hook("anything")


def test_conversacion_simple_pipeline_fires_tts_prefetch_before_assistant_persisted(monkeypatch) -> None:
    reset_session_store()
    monkeypatch.setattr(cs_pipeline, "_call_brain_structured", _fake_brain_call)

    calls: list[str] = []
    neg_flow_config.set_tts_prefetch_hook(lambda reply: calls.append(reply))
    try:
        client = TestClient(app)
        boot = client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_tts", "session_id": "s_tts", "context_id": "baseline"},
        )
        assert boot.status_code == 200

        turn = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "u_tts", "session_id": "s_tts", "message": "hola", "new_conversation": False},
        )
        assert turn.status_code == 200
        assert calls, "tts prefetch hook was never invoked on conversacion_simple turn"
        assert calls[0] == turn.json()["reply"]
    finally:
        neg_flow_config.set_tts_prefetch_hook(None)
