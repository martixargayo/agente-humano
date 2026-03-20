from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from interfaz_usuario import services as interfaz_services
from sessions.redis_store import RedisSessionStore
from sessions.state import get_session_state, get_session_store, reset_session_store, set_session_store


class FakeRedisExpiring:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.now = 0

    def _purge_expired(self) -> None:
        for key in list(self.expirations):
            if self.expirations[key] <= self.now:
                self.store.pop(key, None)
                self.expirations.pop(key, None)

    def advance(self, seconds: int) -> None:
        self.now += seconds
        self._purge_expired()

    @property
    def ttl(self) -> dict[str, int]:
        self._purge_expired()
        return {key: max(0, expiry - self.now) for key, expiry in self.expirations.items() if key in self.store}

    def ping(self):
        self._purge_expired()
        return True

    def get(self, key: str):
        self._purge_expired()
        return self.store.get(key)

    def set(self, key: str, value: str, *, nx: bool | None = None, ex: int | None = None):
        self._purge_expired()
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.expirations[key] = self.now + ex
        return True

    def delete(self, key: str):
        self._purge_expired()
        self.store.pop(key, None)
        self.expirations.pop(key, None)
        return 1

    def expire(self, key: str, seconds: int):
        self._purge_expired()
        if key in self.store:
            self.expirations[key] = self.now + seconds
            return True
        return False

    def scan_iter(self, match: str):
        self._purge_expired()
        prefix = match[:-1] if match.endswith("*") else match
        for key in sorted(self.store):
            if key.startswith(prefix):
                yield key

    def eval(self, script: str, numkeys: int, *keys_and_args):
        self._purge_expired()
        assert numkeys == 1
        key = str(keys_and_args[0])
        token = str(keys_and_args[1])
        if "expire" in script:
            ttl = int(keys_and_args[2])
            if self.store.get(key) == token:
                self.expirations[key] = self.now + ttl
                return 1
            return 0
        if self.store.get(key) == token:
            self.delete(key)
            return 1
        return 0


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_session_runtime():
    previous_env = {
        "SESSION_BOOTSTRAP_TTL_SECONDS": os.environ.get("SESSION_BOOTSTRAP_TTL_SECONDS"),
        "SESSION_ACTIVE_TTL_SECONDS": os.environ.get("SESSION_ACTIVE_TTL_SECONDS"),
        "SESSION_FINALIZED_TTL_SECONDS": os.environ.get("SESSION_FINALIZED_TTL_SECONDS"),
        "SESSION_EXECUTION_LOCK_TTL_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_TTL_SECONDS"),
        "SESSION_EXECUTION_LOCK_REFRESH_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_REFRESH_SECONDS"),
        "SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS"),
        "SESSION_STORE_BACKEND": os.environ.get("SESSION_STORE_BACKEND"),
        "REDIS_URL": os.environ.get("REDIS_URL"),
    }
    reset_session_store()
    get_session_store().clear()
    yield
    reset_session_store()
    get_session_store().clear()
    for key, value in previous_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _set_short_ttls() -> None:
    os.environ["SESSION_BOOTSTRAP_TTL_SECONDS"] = "30"
    os.environ["SESSION_ACTIVE_TTL_SECONDS"] = "120"
    os.environ["SESSION_FINALIZED_TTL_SECONDS"] = "5"
    os.environ["SESSION_EXECUTION_LOCK_TTL_SECONDS"] = "15"
    os.environ["SESSION_EXECUTION_LOCK_REFRESH_SECONDS"] = "5"
    os.environ["SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS"] = "2"


def _bind_fake_redis() -> FakeRedisExpiring:
    fake = FakeRedisExpiring()
    set_session_store(RedisSessionStore(fake))
    return fake


def _patch_successful_turn(monkeypatch, *, reply_text: str = "ok", conversation_id: str = "conv-turn") -> None:
    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        canonical = state.world_state.setdefault("negotiation_canonical", {})
        canonical.setdefault("openai_thread", {"thread_mode": "conversation", "conversation_id": conversation_id, "previous_response_id": None})
        canonical.setdefault("ui_state", {"finish_button_armed": False})
        canonical.setdefault("planner_state", {})
        return (
            reply_text,
            state,
            {
                "trace_count": 1,
                "conversation_id_before": conversation_id,
                "conversation_id_after": conversation_id,
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": "turn-1",
                "entry_contract": {
                    "entry_surface": "interfaz_usuario",
                    "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                    "overrides_applied": False,
                    "optimizer_wrapper_used": False,
                    "new_conversation": False,
                    "clone_used": False,
                    "config_snapshot": {
                        "memory_key": "negotiation_canonical",
                        "thread_mode_default": "conversation",
                        "model_memory": "m1",
                        "model_phase_classifier": "m2",
                        "model_planner": "m3",
                        "model_executor": "m4",
                        "max_recent_messages": 12,
                        "max_executor_recent_turns": 4,
                    },
                },
            },
        )

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", fake_execute_turn_with_contract)


def test_bootstrap_creates_session_with_initial_ttl() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()

    payload = interfaz_services.ensure_session(user_id="u_boot", session_id="s_boot", context_id="baseline_current")
    state = get_session_state("u_boot", "s_boot")
    lifecycle = state.world_state["_session_lifecycle"]

    assert payload["session_id"] == "s_boot"
    assert fake.ttl["session:u_boot:s_boot"] == 30
    assert lifecycle["ttl_scope"] == "bootstrap"
    assert lifecycle["status"] == "active"


def test_successful_turn_renews_active_ttl(monkeypatch) -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    _patch_successful_turn(monkeypatch)

    state = get_session_state("u_turnttl", "s_turnttl")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv-turn", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}
    get_session_store().save(state)
    fake.expire("session:u_turnttl:s_turnttl", 10)

    result = interfaz_services.run_turn(user_id="u_turnttl", session_id="s_turnttl", message="hola")

    assert result["reply"] == "ok"
    assert fake.ttl["session:u_turnttl:s_turnttl"] == 120


def test_inactive_session_expires_cleanly() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    interfaz_services.ensure_session(user_id="u_expire", session_id="s_expire", context_id="baseline_current")

    fake.advance(31)

    assert get_session_store().get(user_id="u_expire", session_id="s_expire") is None


def test_finalized_session_gets_short_cleanup_ttl() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    interfaz_services.ensure_session(user_id="u_final", session_id="s_final", context_id="baseline_current")

    finalized = interfaz_services.finalize_session(user_id="u_final", session_id="s_final")
    state = get_session_store().get(user_id="u_final", session_id="s_final")

    assert finalized["status"] == "finalized"
    assert finalized["ttl_seconds"] == 5
    assert fake.ttl["session:u_final:s_final"] == 5
    assert state is not None
    assert state.world_state["_session_lifecycle"]["status"] == "finalized"


def test_expired_session_does_not_reappear_with_old_continuity_or_context() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    state = get_session_state("u_reuse", "s_reuse")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_old", "previous_response_id": None}}
    state.world_state["negotiation_context"] = {"flow_id": "negociacion", "context_id": "validacion_multicontexto", "context_version": "1.0.0"}
    get_session_store().save(state)
    fake.expire("session:u_reuse:s_reuse", 5)

    fake.advance(6)

    payload = interfaz_services.ensure_session(user_id="u_reuse", session_id="s_reuse", context_id="baseline_current")
    rehydrated = get_session_state("u_reuse", "s_reuse")

    assert payload["conversation_id"] is None
    assert payload["context_id"] == "baseline_current"
    assert rehydrated.world_state["negotiation_context"]["context_id"] == "baseline_current"


def test_new_conversation_after_expiry_starts_clean(monkeypatch) -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    _patch_successful_turn(monkeypatch, conversation_id="conv_clean")

    base = get_session_state("u_clean", "s_clean")
    base.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_old", "previous_response_id": None}}
    get_session_store().save(base)
    fake.expire("session:u_clean:s_clean", 5)
    fake.advance(6)

    payload = interfaz_services.ensure_session(user_id="u_clean", session_id="s_clean", context_id="baseline_current")
    created = interfaz_services.create_new_conversation(user_id="u_clean", base_session_id="s_clean")

    assert payload["conversation_id"] is None
    assert created["conversation_id"] is None
    assert created["session_id"] != "s_clean"


def test_lock_and_session_ttl_do_not_conflict_during_turn(monkeypatch) -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    entered = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        state.world_state.setdefault("negotiation_canonical", {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_lock", "previous_response_id": None}, "planner_state": {}, "ui_state": {}})
        entered.set()
        release.wait(timeout=2)
        return (
            "ok",
            state,
            {
                "trace_count": 1,
                "conversation_id_before": "conv_lock",
                "conversation_id_after": "conv_lock",
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": "turn-lock",
                "entry_contract": {
                    "entry_surface": "interfaz_usuario",
                    "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                    "overrides_applied": False,
                    "optimizer_wrapper_used": False,
                    "new_conversation": False,
                    "clone_used": False,
                    "config_snapshot": {
                        "memory_key": "negotiation_canonical",
                        "thread_mode_default": "conversation",
                        "model_memory": "m1",
                        "model_phase_classifier": "m2",
                        "model_planner": "m3",
                        "model_executor": "m4",
                        "max_recent_messages": 12,
                        "max_executor_recent_turns": 4,
                    },
                },
            },
        )

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", fake_execute_turn_with_contract)

    worker = threading.Thread(target=lambda: interfaz_services.run_turn(user_id="u_lockttl", session_id="s_lockttl", message="hola"))
    worker.start()
    assert entered.wait(timeout=2)

    assert fake.ttl["session:u_lockttl:s_lockttl"] == 120
    assert fake.ttl["session-lock:u_lockttl:s_lockttl"] == 15

    release.set()
    worker.join(timeout=2)

    assert "session-lock:u_lockttl:s_lockttl" not in fake.store
    assert fake.ttl["session:u_lockttl:s_lockttl"] == 120


def test_failed_turn_releases_lock_and_keeps_session_alive(monkeypatch) -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    state = get_session_state("u_retry", "s_retry")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_retry", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}
    get_session_store().save(state)

    def failing_execute_turn_with_contract(*, state, user_message, config, contract):
        raise RuntimeError("boom")

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", failing_execute_turn_with_contract)

    with pytest.raises(RuntimeError):
        interfaz_services.run_turn(user_id="u_retry", session_id="s_retry", message="hola")

    assert "session-lock:u_retry:s_retry" not in fake.store
    assert fake.ttl["session:u_retry:s_retry"] == 120


def test_conversation_id_survives_ttl_renewal_on_reentry() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    state = get_session_state("u_conv", "s_conv")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_survive", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}
    get_session_store().save(state)
    fake.expire("session:u_conv:s_conv", 5)

    payload = interfaz_services.ensure_session(user_id="u_conv", session_id="s_conv", context_id="baseline_current")

    assert payload["conversation_id"] == "conv_survive"
    assert fake.ttl["session:u_conv:s_conv"] == 120


def test_health_endpoint_exposes_session_runtime_config() -> None:
    _set_short_ttls()
    os.environ["SESSION_STORE_BACKEND"] = "memory"
    os.environ.pop("REDIS_URL", None)

    response = client.get("/api/health/session-runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["ttl_seconds"]["bootstrap"] == 30
    assert payload["lock_seconds"]["ttl"] == 15


def test_finalize_endpoint_returns_short_ttl_payload() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    interfaz_services.ensure_session(user_id="u_http", session_id="s_http", context_id="baseline_current")

    response = client.post("/api/interfaz_usuario/sessions/finalize", json={"user_id": "u_http", "session_id": "s_http"})

    assert response.status_code == 200
    assert response.json()["status"] == "finalized"
    assert fake.ttl["session:u_http:s_http"] == 5


def test_restart_logical_with_redis_keeps_active_session_and_renews_ttl() -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    state = get_session_state("u_restart", "s_restart")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_restart", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}
    get_session_store().save(state)
    fake.expire("session:u_restart:s_restart", 5)

    reset_session_store()
    set_session_store(RedisSessionStore(fake))

    payload = interfaz_services.ensure_session(user_id="u_restart", session_id="s_restart", context_id="baseline_current")

    assert payload["conversation_id"] == "conv_restart"
    assert fake.ttl["session:u_restart:s_restart"] == 120


def test_logs_include_ttl_application_and_busy_signal(monkeypatch, caplog) -> None:
    _set_short_ttls()
    fake = _bind_fake_redis()
    entered = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        state.world_state.setdefault("negotiation_canonical", {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_logs", "previous_response_id": None}, "planner_state": {}, "ui_state": {}})
        entered.set()
        release.wait(timeout=2)
        return (
            "ok",
            state,
            {
                "trace_count": 1,
                "conversation_id_before": "conv_logs",
                "conversation_id_after": "conv_logs",
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": "turn-logs",
                "entry_contract": {
                    "entry_surface": "interfaz_usuario",
                    "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                    "overrides_applied": False,
                    "optimizer_wrapper_used": False,
                    "new_conversation": False,
                    "clone_used": False,
                    "config_snapshot": {
                        "memory_key": "negotiation_canonical",
                        "thread_mode_default": "conversation",
                        "model_memory": "m1",
                        "model_phase_classifier": "m2",
                        "model_planner": "m3",
                        "model_executor": "m4",
                        "max_recent_messages": 12,
                        "max_executor_recent_turns": 4,
                    },
                },
            },
        )

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", fake_execute_turn_with_contract)
    caplog.set_level("INFO")

    thread = threading.Thread(target=lambda: interfaz_services.run_turn(user_id="u_logs", session_id="s_logs", message="hola"))
    thread.start()
    assert entered.wait(timeout=2)

    with pytest.raises(HTTPException):
        interfaz_services.run_turn(user_id="u_logs", session_id="s_logs", message="hola otra")

    release.set()
    thread.join(timeout=2)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "session_ttl_applied" in log_text
    assert "interfaz_usuario_turn_busy" in log_text
