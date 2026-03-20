from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interfaz_usuario import services as interfaz_services
from negociacion.optimizador import services as optimizer_services
from sessions.redis_store import RedisSessionStore
from sessions.session_lock import RedisSessionLockManager, SessionBusyError
from sessions.state import (
    SessionEnvelope,
    SessionState,
    export_session_envelope,
    get_session_state,
    get_session_store,
    hydrate_session_state,
    reset_session_store,
    set_session_store,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def ping(self):
        return True

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, *, nx: bool | None = None, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
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
        prefix = match[:-1] if match.endswith("*") else match
        for key in sorted(self.store):
            if key.startswith(prefix):
                yield key

    def eval(self, script: str, numkeys: int, *keys_and_args):
        assert numkeys == 1
        key = str(keys_and_args[0])
        token = str(keys_and_args[1])
        if "expire" in script:
            ttl = int(keys_and_args[2])
            if self.store.get(key) == token:
                self.ttl[key] = ttl
                return 1
            return 0
        if self.store.get(key) == token:
            self.delete(key)
            return 1
        return 0


@pytest.fixture(autouse=True)
def reset_runtime_state():
    previous_env = {
        "SESSION_EXECUTION_LOCK_TTL_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_TTL_SECONDS"),
        "SESSION_EXECUTION_LOCK_REFRESH_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_REFRESH_SECONDS"),
        "SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS": os.environ.get("SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS"),
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


def test_phase4_session_envelope_roundtrip_preserves_openai_thread_continuity() -> None:
    state = SessionState(user_id="u_phase4", session_id="s_phase4")
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {
            "thread_mode": "conversation",
            "conversation_id": "conv_phase4",
            "previous_response_id": "resp_phase4",
        },
        "planner_state": {},
        "ui_state": {},
    }

    envelope = export_session_envelope(state)
    hydrated = hydrate_session_state(envelope)

    thread = hydrated.world_state["negotiation_canonical"]["openai_thread"]
    assert thread["thread_mode"] == "conversation"
    assert thread["conversation_id"] == "conv_phase4"
    assert thread["previous_response_id"] == "resp_phase4"


def test_phase4_hydrate_backfills_thread_payload_when_openai_thread_block_is_missing() -> None:
    envelope = SessionEnvelope.model_validate(
        {
            "schema_version": "session_envelope.v1",
            "identity": {"user_id": "u_backfill", "session_id": "s_backfill"},
            "bindings": {"surface": "interfaz_usuario", "context": None},
            "continuity": {
                "thread_mode": "conversation",
                "conversation_id": "conv_backfill",
                "previous_response_id": None,
            },
            "operational": {
                "summary": "",
                "summary_meta": {},
                "history": [],
                "world_state": {"negotiation_canonical": {"planner_state": {}, "ui_state": {}}},
                "belief_state": {},
                "policy_state": {},
                "last_policy_executed": None,
                "progress_state": {},
                "debug_trace": [],
                "negotiation_objective": "",
                "negotiation_plan": [],
                "current_step_index": 0,
                "step_results": [],
                "sister_option_price": 8000.0,
                "sister_option_repairs": 2000.0,
                "max_total_cost": 10000.0,
                "exit_option": {"label": "Coche hermana", "total_cost": 0.0, "notes": ""},
                "turn_count": 0,
                "last_updated": "2026-03-20T00:00:00+00:00",
            },
        }
    )

    hydrated = hydrate_session_state(envelope)

    thread = hydrated.world_state["negotiation_canonical"]["openai_thread"]
    assert thread["thread_mode"] == "conversation"
    assert thread["conversation_id"] == "conv_backfill"
    assert thread["previous_response_id"] is None


def test_phase4_bootstrap_reentry_preserves_conversation_id_after_redis_roundtrip() -> None:
    fake_redis = FakeRedis()
    set_session_store(RedisSessionStore(fake_redis))

    state = get_session_state(user_id="u_reentry", session_id="s_reentry")
    state.world_state["negotiation_canonical"] = {
        "openai_thread": {
            "thread_mode": "conversation",
            "conversation_id": "conv_reentry",
            "previous_response_id": None,
        },
        "planner_state": {},
        "ui_state": {},
    }
    get_session_store().save(state)

    first = interfaz_services.ensure_session(user_id="u_reentry", session_id="s_reentry", context_id="baseline_current")
    second = interfaz_services.ensure_session(user_id="u_reentry", session_id="s_reentry", context_id="baseline_current")

    assert first["conversation_id"] == "conv_reentry"
    assert second["conversation_id"] == "conv_reentry"


def test_phase4_distinct_sessions_keep_isolated_conversation_ids() -> None:
    first = get_session_state(user_id="u_a", session_id="s_a")
    first.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_a", "previous_response_id": None}}

    second = get_session_state(user_id="u_b", session_id="s_b")
    second.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_b", "previous_response_id": None}}

    first_payload = interfaz_services.ensure_session(user_id="u_a", session_id="s_a", context_id="baseline_current")
    second_payload = interfaz_services.ensure_session(user_id="u_b", session_id="s_b", context_id="baseline_current")

    assert first_payload["conversation_id"] == "conv_a"
    assert second_payload["conversation_id"] == "conv_b"
    assert first_payload["conversation_id"] != second_payload["conversation_id"]


def test_phase4_new_conversation_starts_without_reusing_previous_openai_conversation() -> None:
    state = get_session_state(user_id="u_base", session_id="s_base")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_base", "previous_response_id": None}}

    created = interfaz_services.create_new_conversation(user_id="u_base", base_session_id="s_base")
    new_state = get_session_state(user_id="u_base", session_id=created["session_id"])

    base_thread = state.world_state["negotiation_canonical"]["openai_thread"]
    new_thread = new_state.world_state.get("negotiation_canonical", {}).get("openai_thread") if isinstance(new_state.world_state, dict) else None

    assert base_thread["conversation_id"] == "conv_base"
    assert created["conversation_id"] is None
    assert new_thread is None or new_thread.get("conversation_id") is None


def test_phase5_redis_lock_manager_rejects_second_acquire_for_same_session() -> None:
    manager = RedisSessionLockManager(FakeRedis(), ttl_seconds=30, refresh_seconds=10)

    lease = manager.acquire(user_id="u_lock", session_id="s_lock")
    try:
        with pytest.raises(SessionBusyError):
            manager.acquire(user_id="u_lock", session_id="s_lock")
    finally:
        lease.release_callback()

    next_lease = manager.acquire(user_id="u_lock", session_id="s_lock")
    next_lease.release_callback()


def test_phase5_redis_lock_manager_allows_parallel_distinct_sessions() -> None:
    manager = RedisSessionLockManager(FakeRedis(), ttl_seconds=30, refresh_seconds=10)

    first = manager.acquire(user_id="u_lock", session_id="s_one")
    second = manager.acquire(user_id="u_lock", session_id="s_two")

    first.release_callback()
    second.release_callback()


def test_phase5_run_turn_returns_session_busy_when_same_session_is_already_locked(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    state = get_session_state(user_id="u_busy", session_id="s_busy")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_busy", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        entered.set()
        release.wait(timeout=2)
        return (
            "ok",
            state,
            {
                "trace_count": 1,
                "conversation_id_before": "conv_busy",
                "conversation_id_after": "conv_busy",
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": "turn_busy",
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

    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())
    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", fake_execute_turn_with_contract)

    results: dict[str, object] = {}

    def worker():
        results["first"] = interfaz_services.run_turn(user_id="u_busy", session_id="s_busy", message="hola")

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=2)

    with pytest.raises(HTTPException) as exc:
        interfaz_services.run_turn(user_id="u_busy", session_id="s_busy", message="hola otra vez")

    release.set()
    thread.join(timeout=2)

    assert exc.value.status_code == 423
    assert exc.value.detail["error"] == "session_busy"
    assert results["first"]["reply"] == "ok"


def test_phase5_run_turn_releases_lock_after_failure(monkeypatch) -> None:
    state = get_session_state(user_id="u_fail", session_id="s_fail")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_fail", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}

    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    def failing_execute_turn_with_contract(*, state, user_message, config, contract):
        raise RuntimeError("boom")

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", failing_execute_turn_with_contract)

    with pytest.raises(RuntimeError):
        interfaz_services.run_turn(user_id="u_fail", session_id="s_fail", message="hola")

    def successful_execute_turn_with_contract(*, state, user_message, config, contract):
        return (
            "ok",
            state,
            {
                "trace_count": 1,
                "conversation_id_before": "conv_fail",
                "conversation_id_after": "conv_fail",
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": "turn_ok",
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

    monkeypatch.setattr(interfaz_services, "execute_turn_with_contract", successful_execute_turn_with_contract)
    result = interfaz_services.run_turn(user_id="u_fail", session_id="s_fail", message="hola de nuevo")

    assert result["reply"] == "ok"


def test_phase5_distinct_public_sessions_do_not_block_each_other(monkeypatch) -> None:
    entered = []
    release = threading.Event()

    for session_id in ("s_1", "s_2"):
        state = get_session_state(user_id="u_parallel", session_id=session_id)
        state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": f"conv_{session_id}", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}

    monkeypatch.setattr(interfaz_services, "build_negotiation_pipeline_config", lambda context_id: object())

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        entered.append(state.session_id)
        if len(entered) >= 2:
            release.set()
        release.wait(timeout=2)
        return (
            f"ok-{state.session_id}",
            state,
            {
                "trace_count": 1,
                "conversation_id_before": f"conv_{state.session_id}",
                "conversation_id_after": f"conv_{state.session_id}",
                "previous_response_id_before": None,
                "previous_response_id_after": None,
                "latest_turn_id": f"turn_{state.session_id}",
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

    results: dict[str, object] = {}

    def worker(session_id: str):
        results[session_id] = interfaz_services.run_turn(user_id="u_parallel", session_id=session_id, message="hola")

    first = threading.Thread(target=worker, args=("s_1",))
    second = threading.Thread(target=worker, args=("s_2",))
    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert sorted(entered) == ["s_1", "s_2"]
    assert results["s_1"]["reply"] == "ok-s_1"
    assert results["s_2"]["reply"] == "ok-s_2"


def test_phase5_optimizer_path_reuses_same_session_lock(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    state = get_session_state(user_id="u_opt", session_id="s_opt")
    state.world_state["negotiation_canonical"] = {"openai_thread": {"thread_mode": "conversation", "conversation_id": "conv_opt", "previous_response_id": None}, "planner_state": {}, "ui_state": {}}
    state.world_state["optimizador_sandbox_meta"] = {}

    monkeypatch.setattr(optimizer_services.context_bridge, "ensure_optimizer_session_context", lambda state: {"context_id": "baseline_current"})
    monkeypatch.setattr(optimizer_services, "build_negotiation_pipeline_config", lambda context_id: object())
    monkeypatch.setattr(optimizer_services.experiments_bridge, "resolve_entries", lambda **kwargs: [])
    monkeypatch.setattr(optimizer_services.experiments_bridge, "apply_overrides", lambda base_config, resolved_entries, context_id: (base_config, None))
    monkeypatch.setattr(optimizer_services.storage, "resolve_traces", lambda state: [])
    monkeypatch.setattr(optimizer_services, "list_turns", lambda user_id, session_id, conversation_id=None: [])

    def fake_execute_turn_with_contract(*, state, user_message, config, contract):
        entered.set()
        release.wait(timeout=2)
        return ("ok-opt", state, {"entry_contract": {"entry_surface": "optimizador"}, "trace_count": 0})

    monkeypatch.setattr(optimizer_services, "execute_turn_with_contract", fake_execute_turn_with_contract)

    result_holder: dict[str, object] = {}

    def optimizer_worker():
        result_holder["optimizer"] = optimizer_services.run_sandbox_turn(
            optimizer_session_id="opt-1",
            user_id="u_opt",
            session_id="s_opt",
            message="hola",
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )

    thread = threading.Thread(target=optimizer_worker)
    thread.start()
    assert entered.wait(timeout=2)

    with pytest.raises(HTTPException) as exc:
        interfaz_services.run_turn(user_id="u_opt", session_id="s_opt", message="hola desde ui")

    release.set()
    thread.join(timeout=2)

    assert exc.value.status_code == 423
    assert exc.value.detail["error"] == "session_busy"
    assert result_holder["optimizer"]["reply"] == "ok-opt"
