from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict, deque
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
from negociacion.optimizador.storage import resolve_traces
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS, get_session_state

REPORT_PATH = Path("backend/docs/forensics_effective_context_root_cause_run.json")
ORIGINAL_FREEZE = flow_config.freeze_prompt_artifacts
ORIGINAL_BUILD_MEMORY_INPUT = flow_config.build_memory_input


@dataclass
class RecordedCall:
    node: str
    turn_id: str | None
    payload: dict[str, Any]


@dataclass
class MemoryInputBuild:
    turn_id: str | None
    recent_dialogue_len: int
    memory_working_current: dict[str, Any]
    planner_state_current: dict[str, Any]
    negotiation_state_current: dict[str, Any]


CALLS: list[RecordedCall] = []
PAYLOAD_QUEUE: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
BUILD_INPUTS: list[MemoryInputBuild] = []


def _node_from_output_schema(output_schema_version: str) -> str:
    return {
        "memory.v1": "memory",
        "phase_classifier.v1": "phase_classifier",
        "planner.v3": "planner",
        "executor.v1": "executor",
    }.get(output_schema_version, output_schema_version)


def _patched_freeze_prompt_artifacts(**kwargs: Any):
    frozen = ORIGINAL_FREEZE(**kwargs)
    node = _node_from_output_schema(str(kwargs.get("output_schema_version", "")))
    PAYLOAD_QUEUE[node].append(json.loads(frozen.payload_json))
    return frozen


def _patched_build_memory_input(*args: Any, **kwargs: Any):
    memory_input = ORIGINAL_BUILD_MEMORY_INPUT(*args, **kwargs)
    trace_meta = kwargs.get("trace_meta") if "trace_meta" in kwargs else args[3]
    canonical_state = kwargs.get("canonical_state") if "canonical_state" in kwargs else args[0]
    recent_dialogue = kwargs.get("recent_dialogue") if "recent_dialogue" in kwargs else args[1]
    BUILD_INPUTS.append(
        MemoryInputBuild(
            turn_id=getattr(trace_meta, "turn_id", None),
            recent_dialogue_len=len(recent_dialogue),
            memory_working_current=canonical_state.memory_working.model_dump(mode="json"),
            planner_state_current=canonical_state.planner_state.model_dump(mode="json"),
            negotiation_state_current=canonical_state.negotiation_state.model_dump(mode="json"),
        )
    )
    return memory_input


def _fake_call_structured(client: Any, model: str, messages: list[dict[str, str]], response_model: type[Any], reasoning_effort: str, request_context: dict[str, str], store: bool) -> StructuredCallResult:
    _ = (client, model, messages, reasoning_effort, request_context, store)
    node = {
        "MemoryOutput": "memory",
        "PhaseClassifierOutput": "phase_classifier",
        "PlannerOutput": "planner",
        "ExecutorOutput": "executor",
    }.get(response_model.__name__, response_model.__name__)
    payload = PAYLOAD_QUEUE[node].popleft() if PAYLOAD_QUEUE[node] else {}
    turn_id = payload.get("trace_meta", {}).get("turn_id") if isinstance(payload, dict) else None
    CALLS.append(RecordedCall(node=node, turn_id=turn_id if isinstance(turn_id, str) else None, payload=copy.deepcopy(payload)))

    if node == "memory":
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {
                "current_topic": payload.get("memory_working_current", {}).get("current_topic"),
                "pending_question": payload.get("memory_working_current", {}).get("pending_question"),
                "last_turn_summary": f"recent={len(payload.get('recent_dialogue_short', []))}",
            },
            "negotiation_state": payload.get("scene_state", {}).get("negotiation_state")
            or {
                "status": "active",
                "active_axes": [],
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
    elif node == "phase_classifier":
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"}
    elif node == "planner":
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "avanzar",
            "decision": "ask",
            "content_plan": {"must_include": [], "must_avoid": []},
            "limits": {
                "max_sentences": 3,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": [],
            "done_criteria": ["emitido"],
        }
    else:
        parsed = {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": "respuesta",
            "memory_used": [],
            "refusal_reason": None,
        }

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


def _first_diff(a: Any, b: Any, path: str = "") -> str | None:
    if type(a) != type(b):
        return path or "root"
    if isinstance(a, dict):
        for k in sorted(set(a.keys()) | set(b.keys())):
            if k not in a or k not in b:
                return f"{path}.{k}" if path else k
            d = _first_diff(a[k], b[k], f"{path}.{k}" if path else k)
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}.length"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else (path or "root")


def _calls_for_turn(turn_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for call in CALLS:
        if call.turn_id == turn_id:
            out[call.node] = call.payload
    return out


def _builds_for_turn(turn_id: str) -> list[dict[str, Any]]:
    return [
        {
            "recent_dialogue_len": b.recent_dialogue_len,
            "memory_working_current": b.memory_working_current,
            "planner_state_current": b.planner_state_current,
            "negotiation_state_current": b.negotiation_state_current,
        }
        for b in BUILD_INPUTS
        if b.turn_id == turn_id
    ]


def _run_pair(client: TestClient, *, suffix: str, msg: str, seed_residual_on: str | None = None, stale_canonical_on: str | None = None) -> dict[str, Any]:
    ou, os = f"u_opt_{suffix}", f"s_opt_{suffix}"
    iu, isess = f"u_iu_{suffix}", f"s_iu_{suffix}"

    get_session_state(user_id=ou, session_id=os)
    get_session_state(user_id=iu, session_id=isess)

    if seed_residual_on == "optimizer":
        get_session_state(user_id=ou, session_id=os).world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "residual user"},
            {"role": "assistant", "text": "residual assistant"},
        ]
    if seed_residual_on == "interfaz":
        get_session_state(user_id=iu, session_id=isess).world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "residual user"},
            {"role": "assistant", "text": "residual assistant"},
        ]

    if stale_canonical_on in {"optimizer", "interfaz"}:
        target_state = get_session_state(user_id=ou, session_id=os) if stale_canonical_on == "optimizer" else get_session_state(user_id=iu, session_id=isess)
        canonical = target_state.world_state.get("negotiation_canonical", {})
        if not canonical:
            canonical = flow_config.build_default_canonical_state(session_id=target_state.session_id, user_id=target_state.user_id, thread_mode=flow_config.ThreadMode.conversation).model_dump(mode="json")
        canonical.setdefault("memory_working", {})["current_topic"] = "precio_residual"
        canonical.setdefault("memory_working", {})["last_turn_summary"] = "residual summary"
        canonical.setdefault("planner_state", {})["current_phase"] = "concesiones_y_ajuste_final"
        target_state.world_state["negotiation_canonical"] = canonical

    ro = client.post("/api/optimizador/sandbox/turn", json={
        "optimizer_session_id": "root_cause",
        "user_id": ou,
        "session_id": os,
        "message": msg,
        "conversation_id": None,
        "scope_turn_id": None,
        "repeat_from_turn_id": None,
    })
    ri = client.post("/api/interfaz_usuario/negociacion/turn", json={
        "user_id": iu,
        "session_id": isess,
        "message": msg,
        "new_conversation": False,
    })

    opt_trace = resolve_traces(get_session_state(user_id=ou, session_id=os))[-1]
    iu_trace = resolve_traces(get_session_state(user_id=iu, session_id=isess))[-1]
    opt_calls = _calls_for_turn(opt_trace["turn_id"])
    iu_calls = _calls_for_turn(iu_trace["turn_id"])
    opt_build = _builds_for_turn(opt_trace["turn_id"])
    iu_build = _builds_for_turn(iu_trace["turn_id"])

    node_diffs = {}
    for n in ["memory", "phase_classifier", "planner", "executor"]:
        node_diffs[n] = _first_diff(opt_calls.get(n, {}), iu_calls.get(n, {}))

    return {
        "status_optimizer": ro.status_code,
        "status_interfaz": ri.status_code,
        "node_first_diffs": node_diffs,
        "first_node_divergence": next(({"node": n, "path": d} for n, d in node_diffs.items() if d), None),
        "memory_input_build_first_diff": _first_diff(opt_build[0] if opt_build else {}, iu_build[0] if iu_build else {}),
        "optimizer_build": opt_build,
        "interfaz_build": iu_build,
    }


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    CALLS.clear()
    PAYLOAD_QUEUE.clear()
    BUILD_INPUTS.clear()
    client = TestClient(app)

    central = json.loads(Path("backend/docs/forensics_effective_context_parity_run.json").read_text(encoding="utf-8"))

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), \
         patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze_prompt_artifacts), \
         patch("negociacion.orchestration.flow_config.build_memory_input", _patched_build_memory_input):
        clean = _run_pair(client, suffix="clean", msg="Podemos cerrar en 6500 con transferencia")
        residual_interfaz = _run_pair(client, suffix="residual_iu", msg="Podemos cerrar en 6500 con transferencia", seed_residual_on="interfaz")
        residual_optimizer = _run_pair(client, suffix="residual_opt", msg="Podemos cerrar en 6500 con transferencia", seed_residual_on="optimizer")
        stale_canonical_interfaz = _run_pair(client, suffix="stale_iu", msg="Necesito tu mejor oferta final", stale_canonical_on="interfaz")

        # reset strength on both surfaces
        dirty = get_session_state(user_id="u_reset", session_id="s_reset")
        dirty.world_state["negotiation_canonical_recent_dialogue"] = [{"role": "user", "text": "dirty"}]
        dirty.world_state["negotiation_canonical"] = flow_config.build_default_canonical_state(session_id="s_reset", user_id="u_reset", thread_mode=flow_config.ThreadMode.conversation).model_dump(mode="json")
        dirty.world_state["negotiation_canonical"]["memory_working"]["last_turn_summary"] = "dirty-summary"

        iu_new = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_reset", "session_id": "s_reset", "message": "arrancar limpio", "new_conversation": True})
        opt_new = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "root_cause", "user_id": "u_reset", "session_id": "s_reset"})
        opt_new_sid = opt_new.json()["session_id"]
        opt_new_turn = client.post("/api/optimizador/sandbox/turn", json={
            "optimizer_session_id": "root_cause", "user_id": "u_reset", "session_id": opt_new_sid, "message": "arrancar limpio", "conversation_id": None, "scope_turn_id": None, "repeat_from_turn_id": None
        })

    reset_iu_sid = iu_new.json()["session_id"]
    iu_state = get_session_state(user_id="u_reset", session_id=reset_iu_sid)
    opt_state = get_session_state(user_id="u_reset", session_id=opt_new_sid)

    return {
        "report_version": "root_cause.v1",
        "source_artifact_summary": {
            "central_report_version": central.get("report_version"),
            "turn_count": len(central.get("turns", [])),
            "global_checks": central.get("global_checks"),
            "hidden_continuity_first_divergence": ((central.get("hidden_continuity_skew") or {}).get("first_divergence")),
        },
        "scenarios": {
            "clean": clean,
            "residual_interfaz": residual_interfaz,
            "residual_optimizer": residual_optimizer,
            "stale_canonical_interfaz": stale_canonical_interfaz,
            "reset_strength": {
                "interfaz_new_turn_status": iu_new.status_code,
                "optimizer_new_conversation_status": opt_new.status_code,
                "optimizer_new_turn_status": opt_new_turn.status_code,
                "interfaz_new_session": reset_iu_sid,
                "optimizer_new_session": opt_new_sid,
                "interfaz_recent_dialogue_len": len(iu_state.world_state.get("negotiation_canonical_recent_dialogue", [])),
                "optimizer_recent_dialogue_len": len(opt_state.world_state.get("negotiation_canonical_recent_dialogue", [])),
            },
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
