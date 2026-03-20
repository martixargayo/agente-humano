from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from negociacion.contexts.session_binding import NEGOTIATION_CONTEXT_WORLD_STATE_KEY
from sessions.redis_store import RedisSessionStore
from sessions.state import (
    InMemorySessionStore,
    SessionState,
    configure_session_store_from_env,
    export_session_envelope,
    get_session_state,
    get_session_store,
    hydrate_session_state,
    reset_session_state,
    reset_session_store,
    set_session_store,
)
from sessions.surface_scope import SESSION_SURFACE_WORLD_STATE_KEY


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def ping(self):
        return True

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value
        return True

    def delete(self, key: str):
        self.store.pop(key, None)
        self.ttl.pop(key, None)
        return 1

    def expire(self, key: str, seconds: int):
        if key in self.store:
            self.ttl[key] = seconds
            return True
        return False

    def scan_iter(self, match: str):
        prefix = match[:-1] if match.endswith('*') else match
        for key in sorted(self.store):
            if key.startswith(prefix):
                yield key


client = TestClient(app)


def setup_function() -> None:
    os.environ.pop("SESSION_STORE_BACKEND", None)
    os.environ.pop("REDIS_URL", None)
    reset_session_store()
    get_session_store().clear()



def teardown_function() -> None:
    os.environ.pop("SESSION_STORE_BACKEND", None)
    os.environ.pop("REDIS_URL", None)
    reset_session_store()
    get_session_store().clear()



def test_public_bootstrap_without_ids_creates_unique_server_side_identity() -> None:
    first = client.post("/api/interfaz_usuario/sessions/bootstrap", json={})
    second = client.post("/api/interfaz_usuario/sessions/bootstrap", json={})

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["user_id"] != second_payload["user_id"]
    assert first_payload["session_id"] != second_payload["session_id"]
    assert first_payload["user_id"].startswith("iu_")
    assert first_payload["session_id"].startswith("sess_")



def test_bootstrap_reuses_explicit_identity_for_existing_session() -> None:
    created = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"context_id": "baseline_current"})
    assert created.status_code == 200

    payload = created.json()
    replay = client.post(
        "/api/interfaz_usuario/sessions/bootstrap",
        json={"user_id": payload["user_id"], "session_id": payload["session_id"], "context_id": "baseline_current"},
    )

    assert replay.status_code == 200
    assert replay.json()["user_id"] == payload["user_id"]
    assert replay.json()["session_id"] == payload["session_id"]



def test_session_envelope_preserves_operational_snapshot_and_bindings() -> None:
    state = get_session_state("u_snapshot", "s_snapshot")
    state.summary = "resumen"
    state.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "qué tal"}]
    state.world_state[SESSION_SURFACE_WORLD_STATE_KEY] = "interfaz_usuario"
    state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY] = {
        "flow_id": "negociacion",
        "context_id": "baseline_current",
        "context_version": "1",
    }
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {
            "thread_mode": "conversation",
            "conversation_id": "conv_test",
            "previous_response_id": None,
        },
        "planner_state": {"current_phase": "descubrimiento_y_comprension"},
        "memory_working": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "oferta activa"},
        "negotiation_state": {"status": "active", "active_axes": ["precio"]},
    }
    state.world_state["negotiation_canonical_recent_dialogue"] = [{"role": "assistant", "text": "hola"}]
    state.turn_count = 2

    envelope = export_session_envelope(state)
    rehydrated = hydrate_session_state(envelope)

    assert envelope.schema_version == "session_envelope.v1"
    assert envelope.bindings.surface == "interfaz_usuario"
    assert envelope.bindings.context["context_id"] == "baseline_current"
    assert envelope.continuity.conversation_id == "conv_test"
    assert rehydrated.world_state[SESSION_SURFACE_WORLD_STATE_KEY] == "interfaz_usuario"
    assert rehydrated.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"] == "baseline_current"
    assert rehydrated.world_state["negotiation_canonical"]["openai_thread"]["conversation_id"] == "conv_test"
    assert rehydrated.world_state["negotiation_canonical_recent_dialogue"][0]["role"] == "assistant"
    assert rehydrated.history[-1]["content"] == "qué tal"



def test_inmemory_session_store_roundtrip_keeps_public_runtime_state() -> None:
    store = InMemorySessionStore()
    set_session_store(store)

    state = get_session_state("u_runtime", "s_runtime")
    state.world_state[SESSION_SURFACE_WORLD_STATE_KEY] = "interfaz_usuario"
    state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY] = {
        "flow_id": "negociacion",
        "context_id": "validacion_multicontexto",
        "context_version": "1",
    }
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {
            "thread_mode": "conversation",
            "conversation_id": "conv_runtime",
            "previous_response_id": None,
        },
        "planner_state": {"current_phase": "propuesta_creativa"},
    }
    store.save(state)

    loaded = store.get(user_id="u_runtime", session_id="s_runtime")
    assert loaded is state
    assert loaded.world_state[SESSION_SURFACE_WORLD_STATE_KEY] == "interfaz_usuario"
    assert loaded.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"] == "validacion_multicontexto"
    assert loaded.world_state["negotiation_canonical"]["openai_thread"]["conversation_id"] == "conv_runtime"



def test_redis_session_store_roundtrip_preserves_snapshot_and_bindings() -> None:
    fake_redis = FakeRedis()
    store = RedisSessionStore(fake_redis)
    state = SessionState(user_id="u_redis", session_id="s_redis")
    state.world_state[SESSION_SURFACE_WORLD_STATE_KEY] = "interfaz_usuario"
    state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY] = {
        "flow_id": "negociacion",
        "context_id": "baseline_current",
        "context_version": "1",
    }
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {
            "thread_mode": "conversation",
            "conversation_id": "conv_redis",
            "previous_response_id": "resp_redis",
        },
        "planner_state": {"current_phase": "propuesta_creativa"},
        "memory_working": {"current_topic": "precio", "pending_question": "¿incluye transferencia?", "last_turn_summary": "hay oferta"},
        "negotiation_state": {"status": "active", "active_axes": ["precio"]},
    }
    state.world_state["negotiation_canonical_recent_dialogue"] = [{"role": "assistant", "text": "hola"}]

    store.save(state)
    loaded = store.get(user_id="u_redis", session_id="s_redis")

    assert loaded is not None
    assert loaded.user_id == "u_redis"
    assert loaded.world_state[SESSION_SURFACE_WORLD_STATE_KEY] == "interfaz_usuario"
    assert loaded.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY]["context_id"] == "baseline_current"
    assert loaded.world_state["negotiation_canonical"]["openai_thread"]["conversation_id"] == "conv_redis"
    assert loaded.world_state["negotiation_canonical"]["openai_thread"]["previous_response_id"] == "resp_redis"
    assert loaded.world_state["negotiation_canonical_recent_dialogue"][0]["text"] == "hola"



def test_redis_session_store_survives_process_restart_simulation() -> None:
    fake_redis = FakeRedis()
    first_store = RedisSessionStore(fake_redis)
    state = SessionState(user_id="u_restart", session_id="s_restart")
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_restart", "previous_response_id": None},
        "planner_state": {"current_phase": "descubrimiento_y_comprension"},
    }
    first_store.save(state)

    second_store = RedisSessionStore(fake_redis)
    loaded = second_store.get(user_id="u_restart", session_id="s_restart")

    assert loaded is not None
    assert loaded.world_state["negotiation_canonical"]["openai_thread"]["conversation_id"] == "conv_restart"
    assert loaded.world_state["negotiation_canonical"]["planner_state"]["current_phase"] == "descubrimiento_y_comprension"



def test_redis_session_store_delete_and_touch_behave_as_expected() -> None:
    fake_redis = FakeRedis()
    store = RedisSessionStore(fake_redis)
    state = SessionState(user_id="u_touch", session_id="s_touch")
    store.save(state)

    store.touch(user_id="u_touch", session_id="s_touch", ttl_seconds=900)
    assert fake_redis.ttl["session:u_touch:s_touch"] == 900

    store.delete(user_id="u_touch", session_id="s_touch")
    assert store.get(user_id="u_touch", session_id="s_touch") is None



def test_configure_session_store_from_env_selects_redis_when_requested() -> None:
    os.environ["SESSION_STORE_BACKEND"] = "redis"
    os.environ["REDIS_URL"] = "redis://example"

    import sessions.redis_store as redis_store_module

    original_builder = redis_store_module.build_redis_client_from_url
    fake_redis = FakeRedis()
    redis_store_module.build_redis_client_from_url = lambda url: fake_redis
    try:
        configured = configure_session_store_from_env(force=True)
        assert isinstance(configured, RedisSessionStore)
        configured.save(SessionState(user_id="u_env", session_id="s_env"))
        assert fake_redis.get("session:u_env:s_env") is not None
    finally:
        redis_store_module.build_redis_client_from_url = original_builder


def test_build_redis_client_from_url_applies_fail_fast_timeouts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeRedisFactory:
        @staticmethod
        def from_url(url: str, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return object()

    import sessions.redis_store as redis_store_module

    original_redis = redis_store_module.Redis
    redis_store_module.Redis = FakeRedisFactory
    monkeypatch.setenv("SESSION_REDIS_CONNECT_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("SESSION_REDIS_SOCKET_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("SESSION_REDIS_HEALTH_CHECK_INTERVAL_SECONDS", "45")
    try:
        client = redis_store_module.build_redis_client_from_url("redis://example")
    finally:
        redis_store_module.Redis = original_redis

    assert client is not None
    assert captured["url"] == "redis://example"
    assert captured["decode_responses"] is False
    assert captured["socket_connect_timeout"] == 1.5
    assert captured["socket_timeout"] == 2.5
    assert captured["health_check_interval"] == 45
    assert captured["retry_on_timeout"] is False



def test_configure_session_store_from_env_falls_back_to_memory_without_redis_url() -> None:
    os.environ["SESSION_STORE_BACKEND"] = "auto"
    os.environ.pop("REDIS_URL", None)

    configured = configure_session_store_from_env(force=True)
    assert isinstance(configured, InMemorySessionStore)



def test_reset_session_state_uses_store_abstraction() -> None:
    custom_store = InMemorySessionStore()
    set_session_store(custom_store)

    custom_store.save(SessionState(user_id="u_reset", session_id="s_reset"))
    assert custom_store.get(user_id="u_reset", session_id="s_reset") is not None

    reset_session_state("u_reset", "s_reset")
    assert custom_store.get(user_id="u_reset", session_id="s_reset") is None



def test_public_new_conversation_keeps_user_and_changes_session_id() -> None:
    created = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"context_id": "baseline_current"})
    payload = created.json()

    new_conv = client.post(
        "/api/interfaz_usuario/negociacion/new_conversation",
        json={"user_id": payload["user_id"], "session_id": payload["session_id"]},
    )
    assert new_conv.status_code == 200

    new_payload = new_conv.json()
    assert new_payload["user_id"] == payload["user_id"]
    assert new_payload["session_id"] != payload["session_id"]
