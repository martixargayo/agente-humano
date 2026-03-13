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

REPORT_PATH = Path("backend/docs/forensics_planner_executor_context_skew_run.json")
ORIGINAL_FREEZE = flow_config.freeze_prompt_artifacts
ORIGINAL_BUILD_PLANNER_INPUT = flow_config.build_planner_input

PAYLOADS: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
CALLS: list[dict[str, Any]] = []


def _legacy_build_planner_input(*args: Any, **kwargs: Any):
    payload = ORIGINAL_BUILD_PLANNER_INPUT(*args, **kwargs)
    canonical_state = kwargs.get("canonical_state") if "canonical_state" in kwargs else args[0]
    payload.planner_state.current_turn_goal = canonical_state.planner_state.current_turn_goal
    return payload


def _node_from_schema(schema: str) -> str:
    return {
        "memory.v1": "memory",
        "phase_classifier.v1": "phase_classifier",
        "planner.v3": "planner",
        "executor.v1": "executor",
    }.get(schema, schema)


def _patched_freeze_prompt_artifacts(**kwargs: Any):
    frozen = ORIGINAL_FREEZE(**kwargs)
    node = _node_from_schema(str(kwargs.get("output_schema_version", "")))
    PAYLOADS[node].append(json.loads(frozen.payload_json))
    return frozen


def _fake_call_structured(client: Any, model: str, messages: list[dict[str, str]], response_model: type[Any], reasoning_effort: str, request_context: dict[str, str], store: bool) -> StructuredCallResult:
    _ = (client, model, messages, reasoning_effort, request_context, store)
    node = {
        "MemoryOutput": "memory",
        "PhaseClassifierOutput": "phase_classifier",
        "PlannerOutput": "planner",
        "ExecutorOutput": "executor",
    }.get(response_model.__name__, response_model.__name__)

    payload = PAYLOADS[node].popleft() if PAYLOADS[node] else {}
    turn_id = payload.get("trace_meta", {}).get("turn_id")
    CALLS.append({"node": node, "turn_id": turn_id, "payload": copy.deepcopy(payload)})

    if node == "memory":
        user = (payload.get("user_turn") or {}).get("normalized_text", "")
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {
                "current_topic": "cierre" if "acuerdo" in user or "cerr" in user else "precio",
                "pending_question": None,
                "last_turn_summary": f"recent={len(payload.get('recent_dialogue_short', []))};user={user[:50]}",
            },
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
    elif node == "phase_classifier":
        user = ((payload.get("current_user_turn") or {}).get("normalized_text", "")).lower()
        phase = "formalizacion_del_acuerdo" if any(k in user for k in ["cerramos", "acuerdo", "firm", "transferencia"]) else "concesiones_y_ajuste_final"
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": phase}
    elif node == "planner":
        current_phase = payload.get("current_phase")
        stale_goal = ((payload.get("planner_state") or {}).get("current_turn_goal") or "")
        if current_phase == "formalizacion_del_acuerdo" and stale_goal and "Proponer" in stale_goal:
            goal = stale_goal
            decision = "ask"
        elif current_phase == "formalizacion_del_acuerdo":
            goal = "Confirmar pasos de firma y logística"
            decision = "close"
        else:
            goal = "Proponer un ajuste de oferta condicionado a la inclusión de garantía"
            decision = "counter"
        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": goal,
            "decision": decision,
            "content_plan": {"must_include": ["paso concreto"], "must_avoid": ["rigidez"]},
            "limits": {"max_sentences": 3, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
            "memory_targets": [],
            "done_criteria": ["emitido"],
        }
    else:
        planner_output = payload.get("planner_output") or {}
        goal = planner_output.get("turn_goal", "")
        if "Proponer" in goal:
            spoken = "Propuesta: ajuste condicionado."
        elif "Confirmar pasos de firma" in goal:
            spoken = "Resumen del acuerdo: 7000 EUR con garantía de 1 año. ¿Cómo prefieres organizar el pago y el papeleo?"
        else:
            spoken = "Perfecto, avanzamos."
        parsed = {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": spoken,
            "memory_used": [],
            "refusal_reason": None,
        }

    return StructuredCallResult(parsed_json=parsed, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True, raw_output_text=json.dumps(parsed, ensure_ascii=False))


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


def _calls_for_turn(turn_id: str) -> dict[str, dict[str, Any]]:
    return {c["node"]: c["payload"] for c in CALLS if c.get("turn_id") == turn_id}


def _run_turn_pair(client: TestClient, *, suffix: str, msg: str, inject_interfaz_goal: str | None = None, same_session: bool = False, legacy_planner_input: bool = False) -> dict[str, Any]:
    ou = "u_opt"
    iu = "u_iu"
    osess = f"s_opt_{suffix}" if not same_session else "s_opt_shared"
    isess = f"s_iu_{suffix}" if not same_session else "s_iu_shared"

    get_session_state(user_id=ou, session_id=osess)
    get_session_state(user_id=iu, session_id=isess)

    if inject_interfaz_goal is not None:
        st = get_session_state(user_id=iu, session_id=isess)
        canonical = st.world_state.get("negotiation_canonical")
        if not isinstance(canonical, dict):
            canonical = flow_config.build_default_canonical_state(session_id=isess, user_id=iu, thread_mode=ThreadMode.conversation).model_dump(mode="json")
        canonical.setdefault("planner_state", {})["current_turn_goal"] = inject_interfaz_goal
        st.world_state["negotiation_canonical"] = canonical

    planner_patch = patch("negociacion.orchestration.flow_config.build_planner_input", _legacy_build_planner_input) if legacy_planner_input else None
    if planner_patch is not None:
        planner_patch.start()
    try:
        ro = client.post("/api/optimizador/sandbox/turn", json={"optimizer_session_id": "skew", "user_id": ou, "session_id": osess, "message": msg, "conversation_id": None, "scope_turn_id": None, "repeat_from_turn_id": None})
        ri = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": iu, "session_id": isess, "message": msg, "new_conversation": False})
    finally:
        if planner_patch is not None:
            planner_patch.stop()

    to = resolve_traces(get_session_state(user_id=ou, session_id=osess))[-1]
    ti = resolve_traces(get_session_state(user_id=iu, session_id=isess))[-1]
    po = _calls_for_turn(to["turn_id"])
    pi = _calls_for_turn(ti["turn_id"])

    diffs = {}
    for node in ["phase_classifier", "planner", "executor"]:
        diffs[node] = _first_diff(po.get(node, {}), pi.get(node, {}))

    return {
        "status_optimizer": ro.status_code,
        "status_interfaz": ri.status_code,
        "reply_optimizer": ro.json().get("reply"),
        "reply_interfaz": ri.json().get("reply"),
        "phase_planner_executor_first_diffs": diffs,
        "first_divergence": next(({"node": n, "path": d} for n, d in diffs.items() if d), None),
        "optimizer_planner_phase": (po.get("planner") or {}).get("current_phase"),
        "interfaz_planner_phase": (pi.get("planner") or {}).get("current_phase"),
        "optimizer_planner_goal_in": ((po.get("planner") or {}).get("planner_state") or {}).get("current_turn_goal"),
        "interfaz_planner_goal_in": ((pi.get("planner") or {}).get("planner_state") or {}).get("current_turn_goal"),
    }


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    PAYLOADS.clear()
    CALLS.clear()
    client = TestClient(app)

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze_prompt_artifacts):
        baseline = _run_turn_pair(client, suffix="baseline", msg="Podemos ajustar 7000 con garantía", same_session=False)

        # advance shared sessions to create real planner_state history
        _run_turn_pair(client, suffix="shared1", msg="Podemos ajustar 6900 con garantía", same_session=True)
        phase_transition_shared = _run_turn_pair(client, suffix="shared2", msg="Perfecto, cerramos acuerdo y firma", same_session=True)

        first_turn_fresh = _run_turn_pair(client, suffix="fresh1", msg="Hola, vengo por el coche", same_session=False)
        injected_planner_skew_runtime = _run_turn_pair(
            client,
            suffix="inj_goal_runtime",
            msg="Cerramos acuerdo y firma hoy",
            inject_interfaz_goal="Proponer un ajuste de oferta condicionado a la inclusión de garantía",
            same_session=False,
        )

        injected_planner_skew_legacy = _run_turn_pair(
            client,
            suffix="inj_goal_legacy",
            msg="Cerramos acuerdo y firma hoy",
            inject_interfaz_goal="Proponer un ajuste de oferta condicionado a la inclusión de garantía",
            same_session=False,
            legacy_planner_input=True,
        )

    return {
        "report_version": "planner_executor_context_skew.v1",
        "scenarios": {
            "baseline_clean": baseline,
            "phase_transition_shared_sessions": phase_transition_shared,
            "first_turn_fresh": first_turn_fresh,
            "injected_planner_state_skew_interfaz_runtime": injected_planner_skew_runtime,
            "injected_planner_state_skew_interfaz_legacy_emulation": injected_planner_skew_legacy,
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
