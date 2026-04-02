from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from negociacion.contexts import resolve_negotiation_context
from negociacion.orchestration.context_errors import MissingTurnContextError
from negociacion.orchestration.flow_config import StateRepository, build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS, SessionState, get_session_state

CONTEXTS = ["baseline_current", "validacion_multicontexto", "sala_reuniones"]
client = TestClient(app)


def _fake_call_structured(*args, **kwargs) -> StructuredCallResult:
    _ = (args, kwargs)
    response_model = args[5]
    if response_model.__name__ == "MemoryOutput":
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "diag", "pending_question": None, "last_turn_summary": "diag"},
            "negotiation_state": {
                "status": "active",
                "active_axes": ["precio"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": None,
                "stall_state": {
                    "is_hard_stalemate": False,
                    "stalemate_reason": None,
                    "self_ultimatum_active": False,
                    "self_ultimatum_summary": None,
                },
                "blockers": [],
                "next_open_loop": None,
            },
        }
    elif response_model.__name__ == "PhaseClassifierOutput":
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"}
    elif response_model.__name__ == "PlannerOutput":
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "diag",
            "decision": "ask",
            "content_plan": {"must_include": ["ok"], "must_avoid": ["none"]},
            "limits": {"max_sentences": 2, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
            "memory_targets": [],
            "done_criteria": ["ok"],
        }
    else:
        parsed = {"schema_version": "executor.v1", "status": "deliver", "spoken_text": "ok", "memory_used": [], "refusal_reason": None}

    return StructuredCallResult(
        parsed_json=parsed,
        refusal=None,
        parse_error=None,
        exception_error=None,
        response=None,
        source=StructuredCallSource.model,
        model_called=True,
        raw_output_text=json.dumps(parsed, ensure_ascii=False),
    )


def _persona_policy_hash_for_context(context_id: str) -> str:
    raw = json.loads(resolve_negotiation_context(context_id).persona_path.read_text(encoding="utf-8"))
    policy = raw.get("policy", {}) if isinstance(raw, dict) else {}
    canon = json.dumps(policy, ensure_ascii=False, sort_keys=True)
    return sha256(canon.encode("utf-8")).hexdigest()


def _latest_trace_meta(user_id: str, session_id: str) -> dict:
    state = get_session_state(user_id=user_id, session_id=session_id)
    traces = state.world_state.get("negotiation_canonical_traces", [])
    assert isinstance(traces, list) and traces, "missing_traces"
    latest = traces[-1]
    assert isinstance(latest, dict)
    return latest.get("context_meta", {}) if isinstance(latest.get("context_meta"), dict) else {}


@pytest.fixture(autouse=True)
def _reset_sessions() -> None:
    SESSIONS.clear()


def test_interfaz_usuario_three_contexts_happy_path_coherent(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.orchestration.flow_config._call_structured", _fake_call_structured)

    for context_id in CONTEXTS:
        user_id = f"u_iu_{context_id}"
        session_id = f"s_iu_{context_id}"

        boot = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": user_id, "session_id": session_id, "context_id": context_id})
        assert boot.status_code == 200

        turn = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": user_id, "session_id": session_id, "message": f"hola {context_id}"})
        assert turn.status_code == 200
        meta = _latest_trace_meta(user_id=user_id, session_id=session_id)
        assert meta["effective_context_id"] == context_id
        assert meta["session_bound_context_id"] == context_id
        assert meta["config_context_id"] == context_id
        assert meta["context_id"] == context_id
        assert meta["mismatch_detected"] is False

        state = get_session_state(user_id=user_id, session_id=session_id)
        canonical = state.world_state.get("negotiation_canonical", {})
        persona_policy = canonical.get("persona", {}).get("policy", {}) if isinstance(canonical, dict) else {}
        observed = sha256(json.dumps(persona_policy, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        assert observed == _persona_policy_hash_for_context(context_id)


def test_optimizador_three_contexts_happy_path_coherent(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.orchestration.flow_config._call_structured", _fake_call_structured)
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.apply_overrides", lambda base_config, entries, context_id=None: (base_config, None))
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1})

    for context_id in CONTEXTS:
        user_id = f"u_opt_{context_id}"
        session_id = f"s_opt_{context_id}"

        boot = client.post("/api/optimizador/sessions/bootstrap", json={"user_id": user_id, "session_id": session_id, "context_id": context_id})
        assert boot.status_code == 200

        turn = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": f"opt_{context_id}",
                "user_id": user_id,
                "session_id": session_id,
                "message": f"hola {context_id}",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        assert turn.status_code == 200
        meta = _latest_trace_meta(user_id=user_id, session_id=session_id)
        assert meta["effective_context_id"] == context_id
        assert meta["session_bound_context_id"] == context_id
        assert meta["config_context_id"] == context_id
        assert meta["context_id"] == context_id
        assert meta["mismatch_detected"] is False


def test_legacy_negociar_valid_context_keeps_quartet_aligned(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.orchestration.flow_config._call_structured", _fake_call_structured)

    r = client.post("/negociar", json={"user_id": "u_legacy_ok", "session_id": "s_legacy_ok", "message": "hola", "context_id": "baseline_current"})
    assert r.status_code == 200
    assert r.headers.get("X-Legacy-Negociar") == "deprecated_use_interfaz_usuario_or_optimizador"

    meta = _latest_trace_meta(user_id="u_legacy_ok", session_id="s_legacy_ok")
    assert meta["effective_context_id"] == "baseline_current"
    assert meta["session_bound_context_id"] == "baseline_current"
    assert meta["config_context_id"] == "baseline_current"
    assert meta["context_id"] == "baseline_current"


def test_execute_turn_contract_blocks_inferred_stateful_without_turn_context_before_load_state(monkeypatch) -> None:
    state = SessionState(user_id="u_direct", session_id="s_direct")
    # bind session explicitly to make the call inferred-stateful even if config.stateful=False
    state.world_state["negotiation_context"] = {"flow_id": "negociacion", "context_id": "baseline_current", "context_version": "1.0.0"}

    config = build_negotiation_pipeline_config(context_id="baseline_current", stateful=False)
    called = {"load_state": False}

    def _fail_load_state(*args, **kwargs):
        called["load_state"] = True
        raise AssertionError("load_state_should_not_run")

    monkeypatch.setattr(StateRepository, "load_state", _fail_load_state)

    with pytest.raises(MissingTurnContextError):
        execute_turn_with_contract(
            state=state,
            user_message="hola",
            config=config,
            contract=TurnEntryContract(
                entry_surface="tests",
                entrypoint="/tests/direct",
                overrides_applied=False,
                optimizer_wrapper_used=False,
            ),
            turn_context=None,
        )

    assert called["load_state"] is False


def test_context_switch_attempts_block_and_sequences_stay_isolated(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.orchestration.flow_config._call_structured", _fake_call_structured)

    # interfaz: bind baseline then try sala on same session -> 409
    boot = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u_seq", "session_id": "s_seq", "context_id": "baseline_current"})
    assert boot.status_code == 200
    conflict = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u_seq", "session_id": "s_seq", "context_id": "sala_reuniones"})
    assert conflict.status_code == 409

    # optimizer: same conflict behavior
    boot_opt = client.post("/api/optimizador/sessions/bootstrap", json={"user_id": "u_seq_opt", "session_id": "s_seq_opt", "context_id": "validacion_multicontexto"})
    assert boot_opt.status_code == 200
    conflict_opt = client.post("/api/optimizador/sessions/bootstrap", json={"user_id": "u_seq_opt", "session_id": "s_seq_opt", "context_id": "sala_reuniones"})
    assert conflict_opt.status_code == 409

    # sequential isolation across different sessions/contexts
    pairs = [
        ("u_a", "s_a", "validacion_multicontexto"),
        ("u_b", "s_b", "sala_reuniones"),
        ("u_c", "s_c", "baseline_current"),
    ]
    observed_hashes: dict[str, str] = {}
    for user_id, session_id, context_id in pairs:
        client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": user_id, "session_id": session_id, "context_id": context_id})
        client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": user_id, "session_id": session_id, "message": "hola"})
        state = get_session_state(user_id=user_id, session_id=session_id)
        canonical = state.world_state.get("negotiation_canonical", {})
        persona_policy = canonical.get("persona", {}).get("policy", {}) if isinstance(canonical, dict) else {}
        observed_hash = sha256(json.dumps(persona_policy, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        expected_hash = _persona_policy_hash_for_context(context_id)
        assert observed_hash == expected_hash
        observed_hashes[context_id] = observed_hash

    assert observed_hashes["validacion_multicontexto"] != observed_hashes["sala_reuniones"]
