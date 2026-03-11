from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app
from negociacion.optimizador import datasets_bridge, experiments_bridge, services, storage
from sessions.state import SESSIONS, get_session_state, reset_session_state

client = TestClient(app)


def _seed_turn(*, user_id: str, session_id: str, turn_suffix: str = "1", conversation_id: str = "conv-1", text: str = "hola") -> str:
    state = get_session_state(user_id, session_id)
    turn_id = f"turn_{turn_suffix}_{user_id}_{session_id}"
    trace = {
        "turn_id": turn_id,
        "turn_started_at": f"2026-01-01T00:00:0{turn_suffix}Z",
        "timestamp_utc": f"2026-01-01T00:00:0{turn_suffix}Z",
        "total_latency_ms": 100 + int(turn_suffix),
        "final_status": "deliver",
        "final_reply_text": f"respuesta {turn_suffix}",
        "assistant_turn_emitted": True,
        "guardrails_triggered": False,
        "input_guardrail_decision": "allow",
        "input_guardrail_reasons": [],
        "input_guardrail_triggered": False,
        "input_moderation_used": False,
        "input_moderation_flags": [],
        "output_guardrail_decision": "allow",
        "output_guardrail_reasons": [],
        "output_guardrail_triggered": False,
        "output_guardrail_status_before": "deliver",
        "output_guardrail_status_after": "deliver",
        "output_guardrail_rewrite_applied": False,
        "output_guardrail_enforcement_mode": "observe_only",
        "output_guardrail_enforcement_action": "none",
        "output_guardrail_observed_not_applied_rules": [],
        "output_guardrail_enforced_rules": [],
        "output_guardrail_output_changed": False,
        "output_moderation_used": False,
        "output_moderation_flags": [],
        "conversation_id_after": conversation_id,
        "user_turn": {"raw_text": text},
        "logs": [],
        "nodes": {
            "planner": {
                "status": "plan",
                "source": "model",
                "latency_ms": 10,
                "prompt_version": "planner_v3",
                "output_summary": {"status": "plan"},
                "prompt_artifacts": {
                    "developer_prompt_text": f"DEV {turn_suffix}",
                    "user_prompt_rendered": f"USER {turn_suffix}",
                    "input_payload_json": json.dumps({"turn": turn_suffix}),
                    "model_target": "o4-mini",
                    "prompt_version": "planner_v3",
                    "input_schema_version": "planner_input.v1",
                    "output_schema_version": "planner.v3",
                    "threading_policy": "stateful_sequential",
                    "developer_prompt_hash": f"dev-{turn_suffix}",
                    "user_prompt_hash": f"usr-{turn_suffix}",
                    "payload_hash": f"pay-{turn_suffix}",
                },
            }
        },
        "session_id": session_id,
        "user_id": user_id,
    }
    state.world_state.setdefault("negotiation_canonical_traces", []).append(trace)
    return turn_id


def test_identity_by_user_and_session_and_no_collision():
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="same", turn_suffix="1")
    _seed_turn(user_id="u2", session_id="same", turn_suffix="1")

    sessions = client.get("/api/optimizador/sessions").json()["items"]
    keys = {row["session_key"] for row in sessions}
    assert storage.session_key("u1", "same") in keys
    assert storage.session_key("u2", "same") in keys

    turns_u1 = client.get("/api/optimizador/sessions/u1/same/turns").json()["items"]
    turns_u2 = client.get("/api/optimizador/sessions/u2/same/turns").json()["items"]
    assert len(turns_u1) == 1
    assert len(turns_u2) == 1
    assert turns_u1[0]["turn_id"] != turns_u2[0]["turn_id"]


def test_live_like_refresh_contract_new_turn_is_visible_without_manual_mutation():
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")
    first = client.get("/api/optimizador/sessions/u1/s1/turns").json()["items"]
    assert len(first) == 1
    _seed_turn(user_id="u1", session_id="s1", turn_suffix="2")
    second = client.get("/api/optimizador/sessions/u1/s1/turns").json()["items"]
    assert len(second) == 2


def test_real_sandbox_clone_metadata_for_session_and_conversation():
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="base", turn_suffix="1", conversation_id="conv-a", text="hola a")
    _seed_turn(user_id="u1", session_id="base", turn_suffix="2", conversation_id="conv-b", text="hola b")

    clone_no_conv = client.post(
        "/api/optimizador/sandbox/clone",
        json={"optimizer_session_id": "default", "source_user_id": "u1", "source_session_id": "base"},
    )
    assert clone_no_conv.status_code == 200
    meta1 = clone_no_conv.json()["sandbox_meta"]
    assert meta1["clone_strategy"] == "full_session_with_preferred_conversation"
    assert meta1["source_conversation_id"] is None
    assert "cloned_at" in meta1

    clone_with_conv = client.post(
        "/api/optimizador/sandbox/clone",
        json={
            "optimizer_session_id": "default",
            "source_user_id": "u1",
            "source_session_id": "base",
            "source_conversation_id": "conv-b",
        },
    )
    assert clone_with_conv.status_code == 200
    payload = clone_with_conv.json()
    meta2 = payload["sandbox_meta"]
    assert meta2["source_conversation_id"] == "conv-b"
    assert meta2["preferred_conversation_id"] == "conv-b"

    turns = client.get(f"/api/optimizador/sessions/{payload['user_id']}/{payload['session_id']}/turns").json()["items"]
    assert len(turns) == 2


def test_overrides_scope_and_validation_and_application(monkeypatch):
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")

    bad = client.put(
        "/api/optimizador/overrides/default",
        json={"mode": "sandbox", "entries": [{"category": "config", "key": "unknown", "value": 1, "scope": "this_optimizer_session"}]},
    )
    assert bad.status_code == 400

    ok = client.put(
        "/api/optimizador/overrides/default",
        json={
            "mode": "sandbox",
            "entries": [
                {"category": "config", "key": "model_planner", "value": "gpt-5-mini", "scope": "this_optimizer_session"},
                {"category": "prompt", "key": "planner", "value": "PLANNER OVERRIDE", "scope": "this_conversation", "conversation_id": "conv-1"},
            ],
        },
    )
    assert ok.status_code == 200

    captured = {}

    def fake_run(state, user_message, config):
        captured["model_planner"] = config.model_planner
        captured["prompts_dir"] = config.prompts_dir
        state.world_state.setdefault("negotiation_canonical_traces", []).append(
            {
                "turn_id": "sandbox_1",
                "turn_started_at": "2026-01-01T00:00:03Z",
                "timestamp_utc": "2026-01-01T00:00:03Z",
                "total_latency_ms": 1,
                "final_status": "deliver",
                "final_reply_text": "ok",
                "assistant_turn_emitted": True,
                "guardrails_triggered": False,
                "input_guardrail_decision": "allow",
                "output_guardrail_decision": "allow",
                "output_guardrail_status_before": "deliver",
                "output_guardrail_status_after": "deliver",
                "user_turn": {"raw_text": user_message},
                "logs": [],
                "nodes": {
            "planner": {
                "status": "plan",
                "source": "model",
                "latency_ms": 10,
                "prompt_version": "planner_v3",
                "output_summary": {"status": "plan"},
                "prompt_artifacts": {
                    "developer_prompt_text": "DEV sandbox",
                    "user_prompt_rendered": "USER sandbox",
                    "input_payload_json": json.dumps({"turn": "sandbox"}),
                    "model_target": "o4-mini",
                    "prompt_version": "planner_v3",
                    "input_schema_version": "planner_input.v1",
                    "output_schema_version": "planner.v3",
                    "threading_policy": "stateful_sequential",
                    "developer_prompt_hash": "dev-sandbox",
                    "user_prompt_hash": "usr-sandbox",
                    "payload_hash": "pay-sandbox",
                },
            }
        },
                "conversation_id_after": "conv-1",
            }
        )
        return "ok", state

    
    def _fake_canonical(*, state, user_message, config, channel, execution_profile):
        reply, updated = fake_run(state, user_message, config)
        return type("Canonical", (), {
            "reply": reply,
            "updated_state": updated,
            "effective_config_hash": "hash-test",
            "execution_profile": execution_profile,
            "channel": channel,
            "prompts_dir_effective": str(config.prompts_dir),
        })()

    monkeypatch.setattr(services, "run_negotiation_turn_canonical", _fake_canonical)

    run = client.post(
        "/api/optimizador/sandbox/turn",
        json={"optimizer_session_id": "default", "user_id": "u1", "session_id": "s1", "message": "hola", "conversation_id": "conv-1"},
    )
    assert run.status_code == 200
    assert captured["model_planner"] == "gpt-5-mini"
    assert "optimizador_prompts_" in captured["prompts_dir"]


def test_contextual_phase_cards_and_persona_used_and_tracked(monkeypatch):
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")

    upd = client.put(
        "/api/optimizador/overrides/default",
        json={
            "mode": "sandbox",
            "entries": [
                {
                    "category": "contextual",
                    "key": "phase_cards",
                    "value": {"clima_humano": "OVR CLIMA", "detectar_perfil": "x", "ancla_y_rango": "x", "propuesta_creativa": "x", "cierre_condicional": "x"},
                    "scope": "this_optimizer_session",
                },
                {
                    "category": "contextual",
                    "key": "persona",
                    "value": {
                        "policy": {"tone": "strict", "safety": "high", "goal": "win"},
                        "expressive": {"energy": "low", "warmth": "mid", "directness": "high"},
                    },
                    "scope": "this_optimizer_session",
                },
            ],
        },
    )
    assert upd.status_code == 200

    captured = {}

    def fake_run(state, user_message, config):
        phase_cards = json.loads(Path(config.prompts_dir, "phase_cards.json").read_text(encoding="utf-8"))
        captured["phase_cards"] = phase_cards
        captured["persona_state"] = state.world_state["negotiation_canonical"]["persona"]
        state.world_state.setdefault("negotiation_canonical_traces", []).append(
            {
                "turn_id": "sandbox_ctx",
                "turn_started_at": "2026-01-01T00:00:04Z",
                "timestamp_utc": "2026-01-01T00:00:04Z",
                "total_latency_ms": 1,
                "final_status": "deliver",
                "final_reply_text": "ok",
                "assistant_turn_emitted": True,
                "guardrails_triggered": False,
                "input_guardrail_decision": "allow",
                "output_guardrail_decision": "allow",
                "output_guardrail_status_before": "deliver",
                "output_guardrail_status_after": "deliver",
                "user_turn": {"raw_text": user_message},
                "logs": [],
                "nodes": {
            "planner": {
                "status": "plan",
                "source": "model",
                "latency_ms": 10,
                "prompt_version": "planner_v3",
                "output_summary": {"status": "plan"},
                "prompt_artifacts": {
                    "developer_prompt_text": "DEV sandbox",
                    "user_prompt_rendered": "USER sandbox",
                    "input_payload_json": json.dumps({"turn": "sandbox"}),
                    "model_target": "o4-mini",
                    "prompt_version": "planner_v3",
                    "input_schema_version": "planner_input.v1",
                    "output_schema_version": "planner.v3",
                    "threading_policy": "stateful_sequential",
                    "developer_prompt_hash": "dev-sandbox",
                    "user_prompt_hash": "usr-sandbox",
                    "payload_hash": "pay-sandbox",
                },
            }
        },
                "conversation_id_after": "conv-1",
            }
        )
        return "ok", state

    
    def _fake_canonical(*, state, user_message, config, channel, execution_profile):
        reply, updated = fake_run(state, user_message, config)
        return type("Canonical", (), {
            "reply": reply,
            "updated_state": updated,
            "effective_config_hash": "hash-test",
            "execution_profile": execution_profile,
            "channel": channel,
            "prompts_dir_effective": str(config.prompts_dir),
        })()

    monkeypatch.setattr(services, "run_negotiation_turn_canonical", _fake_canonical)

    r = client.post(
        "/api/optimizador/sandbox/turn",
        json={"optimizer_session_id": "default", "user_id": "u1", "session_id": "s1", "message": "hola", "conversation_id": "conv-1"},
    )
    assert r.status_code == 200
    assert captured["phase_cards"]["clima_humano"] == "OVR CLIMA"
    assert captured["persona_state"]["policy"]["tone"] == "strict"

    turn = services.get_turn("sandbox_ctx")
    assert turn and turn.get("_optimizador", {}).get("applied_overrides", {}).get("contextual")


def test_avatar_and_optimizer_canonical_endpoints_match_on_clean_text_turn(monkeypatch):
    from datetime import datetime, timezone
    from negociacion.orchestration import flow_config as flow

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(flow.uuid, "uuid4", lambda: "turn-fixed-cmp")
    monkeypatch.setattr(flow, "datetime", _FixedDateTime)

    SESSIONS.clear()
    experiments_bridge.reset_state("default")

    user_id = "u_cmp"
    session_id = "s_cmp"
    message = "Hola, quiero hablar del precio."

    avatar_res = client.post(
        "/api/negotiation/turn",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "channel": "avatar",
            "execution_profile": "canonical_negotiation",
        },
    )
    assert avatar_res.status_code == 200
    avatar_payload = avatar_res.json()
    avatar_trace = avatar_payload["trace_probe"]

    # Limpiar sesión para que el optimizador canónico arranque desde estado idéntico.
    reset_session_state(user_id, session_id)

    optimizer_res = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "default",
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    assert optimizer_res.status_code == 200
    optimizer_payload = optimizer_res.json()
    turn_id = optimizer_payload["turn"]["turn_id"]
    turn = client.get(f"/api/optimizador/turns/{turn_id}").json()

    assert optimizer_payload["execution_profile"] == "canonical_negotiation"
    assert avatar_payload["effective_config_hash"] == optimizer_payload["effective_config_hash"]
    assert avatar_payload["prompts_dir_effective"] == optimizer_payload["prompts_dir_effective"]

    assert avatar_trace["conversation_id_before"] == turn.get("conversation_id_before")
    assert avatar_trace["previous_response_id_before"] == turn.get("previous_response_id_before")
    assert avatar_trace["memory_input_hash"] == turn["memory_input_hash"]
    assert avatar_trace["phase_input_hash"] == turn["phase_input_hash"]
    assert avatar_trace["planner_input_hash"] == turn["planner_input_hash"]
    assert avatar_trace["executor_input_hash"] == turn["executor_input_hash"]
    assert avatar_trace["planner_output_hash"] == turn["planner_output_hash"]
    assert avatar_trace["executor_output_before_guardrail_hash"] == turn["executor_output_before_guardrail_hash"]
    assert avatar_trace["final_reply_text"] == turn["final_reply_text"]


def test_contextual_override_invalid_persona_rejected():
    bad = client.put(
        "/api/optimizador/overrides/default",
        json={
            "mode": "sandbox",
            "entries": [
                {"category": "contextual", "key": "persona", "value": {"policy": {}}, "scope": "this_optimizer_session"}
            ],
        },
    )
    assert bad.status_code == 400


def test_compare_and_guardrails_honest_and_cases(monkeypatch, tmp_path):
    SESSIONS.clear()
    monkeypatch.setattr(datasets_bridge, "CASE_FILE", tmp_path / "cases.jsonl")
    a = _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")
    b = _seed_turn(user_id="u1", session_id="s1", turn_suffix="2")

    state = get_session_state("u1", "s1")
    state.world_state["negotiation_canonical_traces"][1]["_optimizador"] = {
        "used_overrides": True,
        "optimizer_session_id": "default",
        "applied_overrides": {"prompt": {"planner": {"scope": "this_optimizer_session", "value": "X"}}, "config": {}, "contextual": {}},
    }

    guard = client.get(f"/api/optimizador/turns/{a}/guardrails").json()
    assert "injection_signals" not in guard["input"]
    assert "internal_terms" not in guard["output"]

    cmp = client.post("/api/optimizador/compare", json={"turn_a": a, "turn_b": b})
    assert cmp.status_code == 200
    body = cmp.json()
    assert body["relationship"]["experiment_kind"] == "baseline_vs_experiment"
    assert "effective_overrides" in body
    assert "node_changes" in body["diff"]
    assert "guardrails" in body["diff"]
    assert "prompt_artifact_changes" in body["diff"]

    save = client.post("/api/optimizador/cases", json={"turn_id": a, "family": "end_to_end", "tags": ["good"], "notes": "ok"})
    assert save.status_code == 200
    listed = client.get("/api/optimizador/cases").json()["items"]
    assert any(item["turn_id"] == a for item in listed)


def test_compare_no_overrides_and_missing_optional_metadata():
    SESSIONS.clear()
    a = _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")
    b = _seed_turn(user_id="u1", session_id="s1", turn_suffix="2")
    body = client.post("/api/optimizador/compare", json={"turn_a": a, "turn_b": b}).json()
    assert body["relationship"]["experiment_kind"] == "baseline_vs_baseline"


def test_override_scopes_resolution_precedence():
    experiments_bridge.reset_state("os1")
    experiments_bridge.update_state(
        "os1",
        {
            "mode": "sandbox",
            "entries": [
                {"category": "config", "key": "model_planner", "value": "base", "scope": "this_optimizer_session"},
                {"category": "config", "key": "model_planner", "value": "conv", "scope": "this_conversation", "conversation_id": "c1"},
                {"category": "config", "key": "model_planner", "value": "turn", "scope": "this_turn", "turn_id": "t1"},
            ],
        },
    )
    resolved = experiments_bridge.resolve_entries(optimizer_session_id="os1", conversation_id="c1", turn_id="t1")
    current = {(e["category"], e["key"]): e["value"] for e in resolved}
    assert current[("config", "model_planner")] == "turn"


def test_new_conversation_endpoint_creates_clean_session():
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="base", turn_suffix="1")
    r = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "default", "user_id": "u1", "session_id": "base"})
    assert r.status_code == 200
    payload = r.json()
    turns = client.get(f"/api/optimizador/sessions/{payload['user_id']}/{payload['session_id']}/turns").json()["items"]
    assert turns == []


def test_repeat_turn_generates_next_version(monkeypatch):
    SESSIONS.clear()
    first_id = _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")

    state = get_session_state("u1", "s1")
    state.world_state["negotiation_canonical_traces"][0]["_optimizador"] = {"versioning": {"base_turn_id": first_id, "version": 1}}

    def fake_run(state, user_message, config):
        state.world_state.setdefault("negotiation_canonical_traces", []).append(
            {
                "turn_id": "turn_repeat",
                "turn_started_at": "2026-01-01T00:00:09Z",
                "timestamp_utc": "2026-01-01T00:00:09Z",
                "total_latency_ms": 1,
                "final_status": "deliver",
                "final_reply_text": "ok",
                "assistant_turn_emitted": True,
                "guardrails_triggered": False,
                "input_guardrail_decision": "allow",
                "output_guardrail_decision": "allow",
                "output_guardrail_status_before": "deliver",
                "output_guardrail_status_after": "deliver",
                "user_turn": {"raw_text": user_message},
                "logs": [],
                "nodes": {
            "planner": {
                "status": "plan",
                "source": "model",
                "latency_ms": 10,
                "prompt_version": "planner_v3",
                "output_summary": {"status": "plan"},
                "prompt_artifacts": {
                    "developer_prompt_text": "DEV sandbox",
                    "user_prompt_rendered": "USER sandbox",
                    "input_payload_json": json.dumps({"turn": "sandbox"}),
                    "model_target": "o4-mini",
                    "prompt_version": "planner_v3",
                    "input_schema_version": "planner_input.v1",
                    "output_schema_version": "planner.v3",
                    "threading_policy": "stateful_sequential",
                    "developer_prompt_hash": "dev-sandbox",
                    "user_prompt_hash": "usr-sandbox",
                    "payload_hash": "pay-sandbox",
                },
            }
        },
                "conversation_id_after": "conv-1",
            }
        )
        return "ok", state

    
    def _fake_canonical(*, state, user_message, config, channel, execution_profile):
        reply, updated = fake_run(state, user_message, config)
        return type("Canonical", (), {
            "reply": reply,
            "updated_state": updated,
            "effective_config_hash": "hash-test",
            "execution_profile": execution_profile,
            "channel": channel,
            "prompts_dir_effective": str(config.prompts_dir),
        })()

    monkeypatch.setattr(services, "run_negotiation_turn_canonical", _fake_canonical)
    run = client.post("/api/optimizador/sandbox/turn", json={"optimizer_session_id": "default", "user_id": "u1", "session_id": "s1", "message": "hola", "conversation_id": "conv-1", "repeat_from_turn_id": first_id})
    assert run.status_code == 200
    turn = services.get_turn("turn_repeat")
    assert turn["_optimizador"]["versioning"]["base_turn_id"] == first_id
    assert turn["_optimizador"]["versioning"]["version"] == 2

def test_confirm_overrides_creates_new_workspace_version():
    SESSIONS.clear()
    _seed_turn(user_id="u1", session_id="s1", turn_suffix="1")

    first = client.get("/api/optimizador/overrides/default").json()
    assert first["workspace_version"] == 1

    confirmed = client.post(
        "/api/optimizador/overrides/default/confirm",
        json={"entries": [{"category": "prompt", "key": "planner", "value": "nuevo", "scope": "this_optimizer_session"}]},
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["workspace_version"] == 2
    assert body["mode"] == "sandbox"
    assert body["committed_entries"][0]["key"] == "planner"


def test_optimizer_can_bootstrap_session_without_avatar_dependency():
    SESSIONS.clear()
    r = client.post("/api/optimizador/sessions/bootstrap", json={"user_id": "u_opt", "session_id": "s_opt"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["user_id"] == "u_opt"
    assert payload["session_id"] == "s_opt"
    sessions = client.get("/api/optimizador/sessions").json()["items"]
    assert any(row["session_key"] == "u_opt::s_opt" for row in sessions)



def test_compare_detects_prompt_artifact_changes():
    SESSIONS.clear()
    a = _seed_turn(user_id="u2", session_id="s2", turn_suffix="1")
    b = _seed_turn(user_id="u2", session_id="s2", turn_suffix="2")
    body = client.post("/api/optimizador/compare", json={"turn_a": a, "turn_b": b}).json()
    assert "planner" in body["diff"]["prompt_artifact_changes"]
    assert body["diff"]["prompt_artifact_changes"]["planner"]["changed"] is True
    assert body["diff"]["prompt_artifact_changes"]["planner"]["fields"]["developer_prompt_text"] is True
