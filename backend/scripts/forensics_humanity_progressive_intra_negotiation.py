from __future__ import annotations

import copy
import json
import re
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
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS, get_session_state

REPORT_PATH = Path("backend/docs/forensics_humanity_progressive_intra_negotiation_run.json")
ORIGINAL_FREEZE = flow_config.freeze_prompt_artifacts
ORIGINAL_BUILD_PLANNER_INPUT = flow_config.build_planner_input
ORIGINAL_BUILD_EXECUTOR_INPUT = flow_config.build_executor_input

PAYLOADS: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
CALLS: list[dict[str, Any]] = []


def _node(output_schema: str) -> str:
    return {
        "memory.v1": "memory",
        "phase_classifier.v1": "phase_classifier",
        "planner.v3": "planner",
        "executor.v1": "executor",
    }.get(output_schema, output_schema)


def _patched_freeze_prompt_artifacts(**kwargs: Any):
    frozen = ORIGINAL_FREEZE(**kwargs)
    node = _node(str(kwargs.get("output_schema_version", "")))
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
    turn_id = (payload.get("trace_meta") or {}).get("turn_id")
    CALLS.append({"node": node, "turn_id": turn_id, "payload": copy.deepcopy(payload)})

    if node == "memory":
        txt = ((payload.get("user_turn") or {}).get("normalized_text") or "").lower()
        recent_len = len(payload.get("recent_dialogue_short") or [])
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [{"event_type": "important_fact", "event_summary": f"recent={recent_len}:{txt[:50]}", "turn_id": turn_id or "t"}],
            "working_memory_new": {
                "current_topic": "cierre" if any(k in txt for k in ["acepto", "cerramos", "firma"]) else "precio",
                "pending_question": None,
                "last_turn_summary": f"recent={recent_len};txt={txt[:32]}",
            },
            "negotiation_state": {
                "status": "active",
                "active_axes": ["precio"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": {"summary": "acuerdo"} if "acepto" in txt else None,
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
        txt = (((payload.get("current_user_turn") or {}).get("normalized_text")) or "").lower()
        phase = "formalizacion_del_acuerdo" if any(k in txt for k in ["acepto", "firma", "cerramos"]) else "concesiones_y_ajuste_final"
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": phase}
    elif node == "planner":
        phase = payload.get("current_phase")
        recent_len = len(payload.get("recent_dialogue_short") or [])
        sel = payload.get("selected_memory") or []
        if phase == "formalizacion_del_acuerdo":
            goal = "Cerrar acuerdo con siguiente paso verificable"
            decision = "close"
        else:
            goal = "Mover negociación con oferta concreta"
            decision = "counter"

        # progressive rigidity proxy: too much accumulated context pushes administrative goal wording
        if recent_len >= 7 and len(sel) >= 3:
            goal = "Formalizar condiciones y ejecutar cierre contractual"

        parsed = {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": goal,
            "decision": decision,
            "content_plan": {
                "must_include": ["paso concreto", "alineación" if recent_len < 7 else "formalización"],
                "must_avoid": ["inventar", "ambigüedad"],
            },
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
        planner_output = payload.get("planner_output") or {}
        turn_goal = str(planner_output.get("turn_goal") or "")
        if "contractual" in turn_goal.lower() or "formalizar" in turn_goal.lower():
            spoken = "Confirmo 7250€ con un año de garantía. Procedamos a formalizar el pago y la firma del contrato para cerrar el acuerdo."
        elif "oferta" in turn_goal.lower():
            spoken = "Te propongo 7000€ con un año de garantía, y vemos juntos cómo cerrarlo bien para ambos."
        else:
            spoken = "Perfecto, avanzamos paso a paso."

        parsed = {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": spoken,
            "memory_used": [m.get("memory_id") for m in payload.get("selected_memory_for_reference", [])],
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


def _rigidity_score(text: str) -> int:
    t = text.lower().strip()
    score = 0
    score += 1 if t.startswith("mi oferta es") else 0
    score += 1 if "procedamos a formalizar" in t else 0
    score += 1 if "cerrar el acuerdo" in t else 0
    score += 1 if re.search(r"\bconfirmo\b", t) else 0
    return score


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in {"turn_id", "timestamp_iso"}:
                continue
            if k in {"last_turn_summary", "memory_summary", "event_summary"}:
                out[k] = "__SUMMARY__"
                continue
            out[k] = _normalize(v)
        return out
    if isinstance(obj, list):
        return [_normalize(x) for x in obj]
    return obj


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


def _calls_for(turn_id: str) -> dict[str, dict[str, Any]]:
    return {c["node"]: c["payload"] for c in CALLS if c.get("turn_id") == turn_id}


def _run_sequence(client: TestClient, *, user_id: str, session_id: str, surface: str, messages: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, msg in enumerate(messages, start=1):
        if surface == "optimizador":
            r = client.post("/api/optimizador/sandbox/turn", json={
                "optimizer_session_id": "humanity-progressive",
                "user_id": user_id,
                "session_id": session_id,
                "message": msg,
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            })
        else:
            r = client.post("/api/interfaz_usuario/negociacion/turn", json={
                "user_id": user_id,
                "session_id": session_id,
                "message": msg,
                "new_conversation": False,
            })
        trace = resolve_traces(get_session_state(user_id=user_id, session_id=session_id))[-1]
        calls = _calls_for(trace["turn_id"])
        planner_payload = calls.get("planner", {})
        executor_payload = calls.get("executor", {})
        reply = r.json().get("reply")
        out.append({
            "turn_index": i,
            "message": msg,
            "status": r.status_code,
            "reply": reply,
            "reply_rigidity_score": _rigidity_score(reply or ""),
            "planner_input": _normalize(planner_payload),
            "planner_output_turn_goal": ((executor_payload.get("planner_output") or {}).get("turn_goal")),
            "planner_recent_dialogue_len": len((planner_payload.get("recent_dialogue_short") or [])),
            "planner_selected_memory_count": len((planner_payload.get("selected_memory") or [])),
            "executor_recent_dialogue_len": len((executor_payload.get("recent_dialogue_short") or [])),
        })
    return out


def _progressive_diffs(opt_turns: list[dict[str, Any]], iu_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for o, i in zip(opt_turns, iu_turns):
        metrics_o = {
            "planner_recent_dialogue_len": o["planner_recent_dialogue_len"],
            "planner_selected_memory_count": o["planner_selected_memory_count"],
            "executor_recent_dialogue_len": o["executor_recent_dialogue_len"],
            "planner_output_turn_goal": o["planner_output_turn_goal"],
        }
        metrics_i = {
            "planner_recent_dialogue_len": i["planner_recent_dialogue_len"],
            "planner_selected_memory_count": i["planner_selected_memory_count"],
            "executor_recent_dialogue_len": i["executor_recent_dialogue_len"],
            "planner_output_turn_goal": i["planner_output_turn_goal"],
        }
        diff = _first_diff(metrics_o, metrics_i)
        out.append({
            "turn_index": o["turn_index"],
            "first_diff": diff,
            "optimizer_rigidity": o["reply_rigidity_score"],
            "interfaz_rigidity": i["reply_rigidity_score"],
            "rigidity_gap_interfaz_minus_optimizer": i["reply_rigidity_score"] - o["reply_rigidity_score"],
            "optimizer_planner_recent": o["planner_recent_dialogue_len"],
            "interfaz_planner_recent": i["planner_recent_dialogue_len"],
        })
    return out


def _clamped_recent_build_planner_input(*args: Any, **kwargs: Any):
    payload = ORIGINAL_BUILD_PLANNER_INPUT(*args, **kwargs)
    payload.recent_dialogue_short = payload.recent_dialogue_short[-4:]
    return payload


def _clamped_recent_build_executor_input(*args: Any, **kwargs: Any):
    payload = ORIGINAL_BUILD_EXECUTOR_INPUT(*args, **kwargs)
    payload.recent_dialogue_short = payload.recent_dialogue_short[-4:]
    return payload


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    CALLS.clear()
    PAYLOADS.clear()

    client = TestClient(app)

    messages = [
        "hola",
        "encantado de conocerte",
        "¿te parece si hablamos de precio?",
        "mi oferta inicial es 6000",
        "yo no bajo de 7500",
        "puedo subir a 7000 con garantía",
        "me sigue pareciendo bajo",
        "acepto tu propuesta",
    ]

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze_prompt_artifacts):
        # Scenario A/B baseline continuous
        o_fresh = _run_sequence(client, user_id="u_opt_a", session_id="s_opt_a", surface="optimizador", messages=messages)
        i_fresh = _run_sequence(client, user_id="u_iu_a", session_id="s_iu_a", surface="interfaz", messages=messages)
        fresh_diffs = _progressive_diffs(o_fresh, i_fresh)

        # Scenario C: progressive hidden residual only on interfaz
        get_session_state(user_id="u_iu_c", session_id="s_iu_c").world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "historial residual 1"},
            {"role": "assistant", "text": "historial residual 2"},
            {"role": "user", "text": "historial residual 3"},
            {"role": "assistant", "text": "historial residual 4"},
        ]
        o_c = _run_sequence(client, user_id="u_opt_c", session_id="s_opt_c", surface="optimizador", messages=messages)
        i_c = _run_sequence(client, user_id="u_iu_c", session_id="s_iu_c", surface="interfaz", messages=messages)
        c_diffs = _progressive_diffs(o_c, i_c)

        # Scenario D: ablation clamp recent windows to test causality of long accumulated window
        with patch("negociacion.orchestration.flow_config.build_planner_input", _clamped_recent_build_planner_input), patch("negociacion.orchestration.flow_config.build_executor_input", _clamped_recent_build_executor_input):
            o_d = _run_sequence(client, user_id="u_opt_d", session_id="s_opt_d", surface="optimizador", messages=messages)
            get_session_state(user_id="u_iu_d", session_id="s_iu_d").world_state["negotiation_canonical_recent_dialogue"] = [
                {"role": "user", "text": "historial residual 1"},
                {"role": "assistant", "text": "historial residual 2"},
                {"role": "user", "text": "historial residual 3"},
                {"role": "assistant", "text": "historial residual 4"},
            ]
            i_d = _run_sequence(client, user_id="u_iu_d", session_id="s_iu_d", surface="interfaz", messages=messages)
            d_diffs = _progressive_diffs(o_d, i_d)

    return {
        "report_version": "humanity_progressive_intra_negotiation.v1",
        "scenarios": {
            "A_baseline_continuous_clean": {
                "optimizer_turns": o_fresh,
                "interfaz_turns": i_fresh,
                "turn_diffs": fresh_diffs,
            },
            "C_progressive_hidden_residual_interfaz": {
                "optimizer_turns": o_c,
                "interfaz_turns": i_c,
                "turn_diffs": c_diffs,
            },
            "D_ablation_clamp_recent_window": {
                "optimizer_turns": o_d,
                "interfaz_turns": i_d,
                "turn_diffs": d_diffs,
            },
        },
        "checks": {
            "A_first_divergence": next((d for d in fresh_diffs if d["first_diff"]), None),
            "C_first_divergence": next((d for d in c_diffs if d["first_diff"]), None),
            "D_first_divergence": next((d for d in d_diffs if d["first_diff"]), None),
            "C_positive_gap_turns": [d["turn_index"] for d in c_diffs if d["rigidity_gap_interfaz_minus_optimizer"] > 0],
            "D_positive_gap_turns": [d["turn_index"] for d in d_diffs if d["rigidity_gap_interfaz_minus_optimizer"] > 0],
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
