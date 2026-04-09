from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import _build_user_turn, build_brain_input, run_conversacion_simple_turn
from conversacion_simple.nodes import TraceMeta
from conversacion_simple.services import build_conversacion_simple_turn_context
from conversacion_simple.state import build_default_conversation_simple_canonical_state
from negociacion.state.shared_types import ThreadMode
from sessions.state import SessionState


def _rich_assets() -> tuple[dict, dict, dict]:
    assets_dir = (
        Path(__file__).resolve().parents[1]
        / "conversacion_simple"
        / "contexts"
        / "negociacion_sala_reuniones"
        / "assets"
    )
    persona = json.loads((assets_dir / "persona.json").read_text(encoding="utf-8"))
    brief = json.loads((assets_dir / "conversation_brief.json").read_text(encoding="utf-8"))
    phase_cards = json.loads((assets_dir / "phase_cards.json").read_text(encoding="utf-8"))
    return persona, brief, phase_cards


def _extract_brain_input_from_trace(updated_state: SessionState, traces_key: str) -> dict:
    trace = updated_state.world_state[traces_key][-1]
    provider_request = trace["memory_observability"]["brain_provider_request"]
    user_content = provider_request["input"][1]["content"]
    raw_json = user_content.split("<brain_input_json>\n", 1)[1].split("\n</brain_input_json>", 1)[0]
    return json.loads(raw_json)


def _bind_cs_context(state: SessionState, context_id: str = "negociacion_sala_reuniones") -> None:
    state.world_state["_session_surface"] = "interfaz_usuario"
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def test_rich_assets_survive_default_state_and_brain_input() -> None:
    persona_raw, brief_raw, phase_raw = _rich_assets()

    canonical = build_default_conversation_simple_canonical_state(
        session_id="s_assets",
        user_id="u_assets",
        thread_mode=ThreadMode.conversation,
        context_id="negociacion_sala_reuniones",
    )
    assert canonical.persona.model_dump(mode="json") == persona_raw
    assert canonical.conversation_brief.model_dump(mode="json") == brief_raw
    assert canonical.phase_cards.model_dump(mode="json") == phase_raw

    brain_input = build_brain_input(
        canonical_state=canonical,
        recent_dialogue=[],
        user_turn=_build_user_turn("hola", "2026-04-09T00:00:00Z"),
        trace_meta=TraceMeta(
            turn_id="turn-assets",
            prompt_version="brain_v1",
            schema_version="brain_input.v1",
            model_target="gpt-5.4",
        ),
    )
    dumped = json.loads(brain_input.model_dump_json())
    assert dumped["persona"] == persona_raw
    assert dumped["conversation_brief"] == brief_raw
    assert dumped["phase_cards"] == phase_raw


class _FakeResponse:
    id = "resp_assets"
    output_text = json.dumps(
        {
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "ok"},
            "state_patch": {
                "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "x"},
                "memory_working": {"current_topic": None, "pending_question": None, "last_turn_summary": "s"},
                "memory_episodic_append": [],
            },
            "observability": {"rationale_summary": "ok"},
        }
    )


class _FakeResponses:
    def create(self, **kwargs):
        _ = kwargs
        return _FakeResponse()


class _FakeClient:
    responses = _FakeResponses()


def test_brain_provider_request_keeps_rich_assets_for_interfaz_y_optimizador(monkeypatch) -> None:
    persona_raw, brief_raw, phase_raw = _rich_assets()
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._build_client", lambda: _FakeClient())
    monkeypatch.setenv("CONVERSACION_SIMPLE_TRACE_FORENSIC", "1")

    config = build_conversacion_simple_pipeline_config(context_id="negociacion_sala_reuniones", stateful=True)

    surfaces = [
        ("interfaz_usuario", "/api/interfaz_usuario/negociacion/turn"),
        ("optimizador", "/api/optimizador/sandbox/turn"),
    ]

    for surface, entrypoint in surfaces:
        state = SessionState(user_id=f"u_{surface}", session_id=f"s_{surface}")
        _bind_cs_context(state)
        state.world_state["_session_surface"] = surface
        turn_context = build_conversacion_simple_turn_context(
            state=state,
            entrypoint=entrypoint,
            entry_surface=surface,
            context_source="test",
            requested_context_id="negociacion_sala_reuniones",
        )

        _reply, updated, _meta = run_conversacion_simple_turn(
            state=state,
            user_message="hola",
            config=config,
            turn_context=turn_context,
        )

        payload = _extract_brain_input_from_trace(updated, config.traces_key)
        assert payload["persona"] == persona_raw
        assert payload["conversation_brief"] == brief_raw
        assert payload["phase_cards"] == phase_raw

        # Muestra explícita de preservación de estructura compleja/nueva.
        assert payload["persona"]["decision_policy"]["time_slot_preference"]["general_preference"]
        assert payload["conversation_brief"]["operational_rules"]["time_computation_rules"]
        assert payload["phase_cards"]["phases"]["clima_humano"]["objective"]
