from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict, deque
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
from negociacion.state.shared_types import StructuredCallSource, ThreadMode
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS, get_session_state

REPORT_PATH = Path("backend/docs/forensics_humanity_residual_planner_executor_run.json")
ORIGINAL_FREEZE = flow_config.freeze_prompt_artifacts

PAYLOAD_QUEUE: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
CALLS: list[dict[str, Any]] = []


def _node(schema_version: str) -> str:
    return {
        "memory.v1": "memory",
        "phase_classifier.v1": "phase_classifier",
        "planner.v3": "planner",
        "executor.v1": "executor",
    }.get(schema_version, schema_version)


def _patched_freeze_prompt_artifacts(**kwargs: Any):
    frozen = ORIGINAL_FREEZE(**kwargs)
    payload = json.loads(frozen.payload_json)
    PAYLOAD_QUEUE[_node(str(kwargs.get("output_schema_version", "")))].append(payload)
    return frozen


def _fake_call_structured(client: Any, model: str, messages: list[dict[str, str]], response_model: type[Any], reasoning_effort: str, request_context: dict[str, str], store: bool) -> StructuredCallResult:
    _ = (client, model, messages, reasoning_effort, request_context, store)
    node_name = {
        "MemoryOutput": "memory",
        "PhaseClassifierOutput": "phase_classifier",
        "PlannerOutput": "planner",
        "ExecutorOutput": "executor",
    }.get(response_model.__name__, response_model.__name__)

    payload = PAYLOAD_QUEUE[node_name].popleft() if PAYLOAD_QUEUE[node_name] else {}
    turn_id = (payload.get("trace_meta") or {}).get("turn_id")
    CALLS.append({"node": node_name, "turn_id": turn_id, "payload": copy.deepcopy(payload)})

    if node_name == "memory":
        text = (payload.get("user_turn") or {}).get("normalized_text", "").lower()
        recent_len = len(payload.get("recent_dialogue_short") or [])
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [{"event_type": "important_fact", "event_summary": f"recent={recent_len};{text[:40]}", "turn_id": turn_id or "t"}],
            "working_memory_new": {"current_topic": "cierre" if "acepto" in text else "precio", "pending_question": None, "last_turn_summary": f"recent={recent_len}"},
            "negotiation_state": {
                "status": "active",
                "active_axes": ["precio"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": {"summary": "acuerdo"} if "acepto" in text else None,
                "stall_state": {"is_hard_stalemate": False, "stalemate_reason": None, "self_ultimatum_active": False, "self_ultimatum_summary": None},
                "blockers": [],
                "next_open_loop": None,
            },
        }
    elif node_name == "phase_classifier":
        text = ((payload.get("current_user_turn") or {}).get("normalized_text", "")).lower()
        phase = "formalizacion_del_acuerdo" if "acepto" in text or "firma" in text else "concesiones_y_ajuste_final"
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": phase}
    elif node_name == "planner":
        recent_len = len(payload.get("recent_dialogue_short") or [])
        current_phase = payload.get("current_phase")
        selected = payload.get("selected_memory") or []
        has_deep_history = recent_len >= 7 or len(selected) >= 3
        if current_phase == "formalizacion_del_acuerdo":
            goal = "Confirmar y coordinar cierre con pasos concretos"
            decision = "close"
        else:
            goal = "Presentar oferta clara y natural"
            decision = "counter"
        if has_deep_history:
            goal = "Formalizar condiciones y cerrar acuerdo"
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": goal,
            "decision": decision,
            "content_plan": {"must_include": ["siguiente paso"], "must_avoid": ["ambigüedad"]},
            "limits": {"max_sentences": 3, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
            "memory_targets": [],
            "done_criteria": ["emitido"],
        }
    else:
        planner_output = payload.get("planner_output") or {}
        goal = planner_output.get("turn_goal", "")
        if "Formalizar condiciones" in goal:
            spoken = "Confirmo condiciones y procedamos a formalizar el pago y firma para cerrar el acuerdo."
            style = "rigid_admin"
        elif "Presentar oferta" in goal:
            spoken = "Te propongo 7250€ con un año de garantía, ¿cómo lo ves?"
            style = "human"
        else:
            spoken = "Perfecto, cerramos y vemos los pasos de firma."
            style = "neutral"
        parsed = {"schema_version": "executor.v1", "status": "deliver", "spoken_text": spoken, "memory_used": [style], "refusal_reason": None}

    return StructuredCallResult(parsed_json=parsed, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True, raw_output_text=json.dumps(parsed, ensure_ascii=False))


def _calls(turn_id: str) -> dict[str, dict[str, Any]]:
    return {c["node"]: c["payload"] for c in CALLS if c.get("turn_id") == turn_id}


def _first_diff(a: Any, b: Any, path: str = "") -> str | None:
    if type(a) != type(b):
        return path or "root"
    if isinstance(a, dict):
        for k in sorted(set(a.keys()) | set(b.keys())):
            if k in {"turn_id", "timestamp_iso"}:
                continue
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


def _mini_episode(client: TestClient, *, user_id: str, session_id: str, optimizer: bool, optimizer_session_id: str = "forensic") -> dict[str, Any]:
    msgs = [
        "hola",
        "te propongo 7000 con garantía",
        "acepto tu propuesta",
    ]
    results = []
    for msg in msgs:
        if optimizer:
            r = client.post("/api/optimizador/sandbox/turn", json={"optimizer_session_id": optimizer_session_id, "user_id": user_id, "session_id": session_id, "message": msg, "conversation_id": None, "scope_turn_id": None, "repeat_from_turn_id": None})
        else:
            r = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": user_id, "session_id": session_id, "message": msg, "new_conversation": False})
        trace = resolve_traces(get_session_state(user_id=user_id, session_id=session_id))[-1]
        p = _calls(trace["turn_id"])
        planner = p.get("planner", {})
        executor = p.get("executor", {})
        results.append({
            "msg": msg,
            "status": r.status_code,
            "reply": r.json().get("reply"),
            "planner_recent_dialogue_len": len(planner.get("recent_dialogue_short") or []),
            "planner_selected_memory_count": len(planner.get("selected_memory") or []),
            "planner_turn_goal": (planner.get("planner_state") or {}).get("current_turn_goal"),
            "executor_recent_dialogue_len": len(executor.get("recent_dialogue_short") or []),
        })
    return {"turns": results}


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    PAYLOAD_QUEUE.clear()
    CALLS.clear()
    client = TestClient(app)

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze_prompt_artifacts):
        # Scenario 1: both fresh per episode
        s1 = []
        for i in range(3):
            o_new = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "forensic", "user_id": "u_opt1", "session_id": "s_opt1"}).json()["session_id"]
            i_new = client.post("/api/interfaz_usuario/negociacion/new_conversation", json={"user_id": "u_iu1", "session_id": "s_iu1"}).json()["session_id"]
            s1.append({
                "episode": i + 1,
                "optimizer": _mini_episode(client, user_id="u_opt1", session_id=o_new, optimizer=True),
                "interfaz": _mini_episode(client, user_id="u_iu1", session_id=i_new, optimizer=False),
            })

        # Scenario 2: progressive reuse only on interfaz; optimizer fresh per episode
        s2 = []
        shared_iu = "s_iu_reuse"
        for i in range(4):
            o_new = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "forensic", "user_id": "u_opt2", "session_id": "s_opt2"}).json()["session_id"]
            s2.append({
                "episode": i + 1,
                "optimizer": _mini_episode(client, user_id="u_opt2", session_id=o_new, optimizer=True),
                "interfaz": _mini_episode(client, user_id="u_iu2", session_id=shared_iu, optimizer=False),
            })

        # Scenario 3: control symmetry, both reuse
        s3 = []
        for i in range(3):
            s3.append({
                "episode": i + 1,
                "optimizer": _mini_episode(client, user_id="u_opt3", session_id="s_opt_reuse", optimizer=True),
                "interfaz": _mini_episode(client, user_id="u_iu3", session_id="s_iu_reuse2", optimizer=False),
            })

        # Scenario 4: auto-reset boundary (interfaz)
        boundary_state = get_session_state(user_id="u_boundary", session_id="s_boundary")
        boundary_state.world_state["negotiation_canonical"] = flow_config.build_default_canonical_state(session_id="s_boundary", user_id="u_boundary", thread_mode=ThreadMode.conversation).model_dump(mode="json")
        boundary_state.world_state["negotiation_canonical"]["planner_state"]["current_phase"] = "formalizacion_del_acuerdo"
        boundary_state.world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "acepto"},
            {"role": "assistant", "text": "cerramos"},
            {"role": "user", "text": "ok"},
            {"role": "assistant", "text": "firma"},
        ]
        boundary = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_boundary", "session_id": "s_boundary", "message": "hola, vengo a ver el coche", "new_conversation": False}).json()

    def episode_diff_path(ep: dict[str, Any]) -> str | None:
        o = ep["optimizer"]["turns"][-1]
        i = ep["interfaz"]["turns"][-1]
        return _first_diff(o, i)

    s2_diffs = [{"episode": ep["episode"], "first_diff": episode_diff_path(ep)} for ep in s2]

    return {
        "report_version": "humanity_residual_planner_executor.v1",
        "scenarios": {
            "both_fresh_per_episode": s1,
            "interfaz_reuse_vs_optimizer_fresh": s2,
            "both_reuse_control": s3,
            "interfaz_boundary_auto_reset": boundary,
        },
        "checks": {
            "s2_first_progressive_diff": next((d for d in s2_diffs if d["first_diff"]), None),
            "s2_diffs": s2_diffs,
            "boundary_auto_reset_applied": bool(boundary.get("auto_reset_applied")),
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
