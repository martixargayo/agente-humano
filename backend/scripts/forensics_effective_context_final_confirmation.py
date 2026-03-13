from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from negociacion.orchestration import flow_config
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS

REPORT_PATH = Path("backend/docs/forensics_effective_context_final_confirmation_run.json")
ORIGINAL_BUILD_MEMORY_INPUT = flow_config.build_memory_input


@dataclass
class BuildCapture:
    session_id: str
    recent_dialogue_len: int


BUILDS: list[BuildCapture] = []


def _patched_build_memory_input(*args: Any, **kwargs: Any):
    memory_input = ORIGINAL_BUILD_MEMORY_INPUT(*args, **kwargs)
    canonical_state = kwargs.get("canonical_state") if "canonical_state" in kwargs else args[0]
    recent_dialogue = kwargs.get("recent_dialogue") if "recent_dialogue" in kwargs else args[1]
    BUILDS.append(BuildCapture(session_id=canonical_state.session.session_id, recent_dialogue_len=len(recent_dialogue)))
    return memory_input


def _fake_call_structured(client: Any, model: str, messages: list[dict[str, str]], response_model: type[Any], reasoning_effort: str, request_context: dict[str, str], store: bool) -> StructuredCallResult:
    _ = (client, model, messages, reasoning_effort, request_context, store)
    name = response_model.__name__
    if name == "MemoryOutput":
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "precio", "pending_question": None, "last_turn_summary": "ok"},
            "negotiation_state": {
                "status": "active",
                "active_axes": ["precio"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": None,
                "stall_state": {"is_hard_stalemate": False, "stalemate_reason": None, "self_ultimatum_active": False, "self_ultimatum_summary": None},
                "blockers": [],
                "next_open_loop": None,
            },
        }
    elif name == "PhaseClassifierOutput":
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"}
    elif name == "PlannerOutput":
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "avanzar",
            "decision": "ask",
            "content_plan": {"must_include": [], "must_avoid": []},
            "limits": {"max_sentences": 3, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
            "memory_targets": [],
            "done_criteria": ["ok"],
        }
    else:
        parsed = {"schema_version": "executor.v1", "status": "deliver", "spoken_text": "ok", "memory_used": [], "refusal_reason": None}

    return StructuredCallResult(parsed_json=parsed, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True, raw_output_text=json.dumps(parsed, ensure_ascii=False))


def _trial_shared_interfaz_vs_fresh_optimizer(client: TestClient, trials: int = 8) -> dict[str, Any]:
    interfaz_lens = []
    optimizer_lens = []

    for i in range(trials):
        # interfaz keeps reusing same session (common manual flow)
        before = len(BUILDS)
        client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_interfaz", "session_id": "interfaz-main", "message": f"Caso {i} oferta 6500", "new_conversation": False})
        interfaz_lens.append(BUILDS[before].recent_dialogue_len)

        # optimizer starts clean sessions (common optimizer experimentation flow)
        nc = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "final", "user_id": "u_opt", "session_id": "opt-main"}).json()
        before = len(BUILDS)
        client.post("/api/optimizador/sandbox/turn", json={
            "optimizer_session_id": "final",
            "user_id": "u_opt",
            "session_id": nc["session_id"],
            "message": f"Caso {i} oferta 6500",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        })
        optimizer_lens.append(BUILDS[before].recent_dialogue_len)

    return {
        "interfaz_recent_dialogue_len": interfaz_lens,
        "optimizer_recent_dialogue_len": optimizer_lens,
        "interfaz_contaminated_first_turns": sum(1 for x in interfaz_lens if x > 1),
        "optimizer_contaminated_first_turns": sum(1 for x in optimizer_lens if x > 1),
    }


def _trial_both_fresh(client: TestClient, trials: int = 8) -> dict[str, Any]:
    interfaz_lens = []
    optimizer_lens = []

    for i in range(trials):
        iu = client.post("/api/interfaz_usuario/negociacion/new_conversation", json={"user_id": "u_interfaz_fresh", "session_id": "interfaz-main"}).json()
        before = len(BUILDS)
        client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_interfaz_fresh", "session_id": iu["session_id"], "message": f"Caso {i} oferta 6500", "new_conversation": False})
        interfaz_lens.append(BUILDS[before].recent_dialogue_len)

        nc = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "final", "user_id": "u_opt_fresh", "session_id": "opt-main"}).json()
        before = len(BUILDS)
        client.post("/api/optimizador/sandbox/turn", json={
            "optimizer_session_id": "final",
            "user_id": "u_opt_fresh",
            "session_id": nc["session_id"],
            "message": f"Caso {i} oferta 6500",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        })
        optimizer_lens.append(BUILDS[before].recent_dialogue_len)

    return {
        "interfaz_recent_dialogue_len": interfaz_lens,
        "optimizer_recent_dialogue_len": optimizer_lens,
        "interfaz_contaminated_first_turns": sum(1 for x in interfaz_lens if x > 1),
        "optimizer_contaminated_first_turns": sum(1 for x in optimizer_lens if x > 1),
    }


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    BUILDS.clear()
    client = TestClient(app)

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), patch("negociacion.orchestration.flow_config.build_memory_input", _patched_build_memory_input):
        asym = _trial_shared_interfaz_vs_fresh_optimizer(client)
        clean = _trial_both_fresh(client)

    return {
        "report_version": "final_confirmation.v1",
        "central_artifact_reference": "backend/docs/forensics_effective_context_parity_run.json",
        "scenarios": {
            "usage_pattern_asymmetry": asym,
            "both_fresh_control": clean,
        },
        "conclusion_checks": {
            "asymmetry_exists_under_usage_pattern": asym["interfaz_contaminated_first_turns"] > asym["optimizer_contaminated_first_turns"],
            "parity_recovers_when_both_fresh": clean["interfaz_contaminated_first_turns"] == clean["optimizer_contaminated_first_turns"] == 0,
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
