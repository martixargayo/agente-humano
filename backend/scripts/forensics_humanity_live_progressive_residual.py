from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
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
from sessions.state import SESSIONS, get_session_state

REPORT_PATH = Path("backend/docs/forensics_humanity_live_progressive_residual_run.json")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"turn_id", "timestamp_iso", "response_id", "conversation_id", "session_id"}:
                continue
            if key in {"last_turn_summary", "memory_summary", "event_summary"}:
                out[key] = "__SUMMARY__"
                continue
            out[key] = _normalize(item)
        return out
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _first_diff(a: Any, b: Any, path: str = "") -> str | None:
    if type(a) is not type(b):
        return path or "root"
    if isinstance(a, dict):
        keys = sorted(set(a.keys()) | set(b.keys()))
        for key in keys:
            if key not in a or key not in b:
                return f"{path}.{key}" if path else key
            diff = _first_diff(a[key], b[key], f"{path}.{key}" if path else key)
            if diff:
                return diff
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}.length"
        for idx, (left, right) in enumerate(zip(a, b)):
            diff = _first_diff(left, right, f"{path}[{idx}]")
            if diff:
                return diff
        return None
    return None if a == b else (path or "root")


def _rigidity_markers(text: str) -> dict[str, int]:
    t = (text or "").lower()
    administrative = [
        "mi oferta es",
        "confirmo",
        "procedamos a formalizar",
        "formalizar",
        "contrato",
        "cláusula",
    ]
    humane = [
        "entiendo",
        "gracias",
        "si te parece",
        "podemos",
        "me encaja",
        "te propongo",
    ]
    admin_hits = sum(1 for marker in administrative if marker in t)
    humane_hits = sum(1 for marker in humane if marker in t)
    return {
        "admin_hits": admin_hits,
        "humane_hits": humane_hits,
        "rigidity_score": admin_hits - humane_hits,
    }


def _payload_from_trace_node(node: dict[str, Any]) -> dict[str, Any]:
    artifacts = node.get("prompt_artifacts") if isinstance(node, dict) else None
    if not isinstance(artifacts, dict):
        return {}
    payload_json = artifacts.get("input_payload_json")
    if not isinstance(payload_json, str) or not payload_json.strip():
        return {}
    try:
        decoded = json.loads(payload_json)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _turn_record(trace: dict[str, Any], message: str, reply: str, status: int, turn_index: int) -> dict[str, Any]:
    nodes = trace.get("nodes", {}) if isinstance(trace, dict) else {}
    planner_node = nodes.get("planner") if isinstance(nodes, dict) else {}
    executor_node = nodes.get("executor") if isinstance(nodes, dict) else {}
    memory_node = nodes.get("memory") if isinstance(nodes, dict) else {}

    planner_input = _normalize(_payload_from_trace_node(planner_node if isinstance(planner_node, dict) else {}))
    executor_input = _normalize(_payload_from_trace_node(executor_node if isinstance(executor_node, dict) else {}))
    memory_input = _normalize(_payload_from_trace_node(memory_node if isinstance(memory_node, dict) else {}))

    planner_output = _normalize((planner_node or {}).get("final_emitted_output_summary") if isinstance(planner_node, dict) else {})
    executor_output = _normalize((executor_node or {}).get("final_emitted_output_summary") if isinstance(executor_node, dict) else {})

    rigidity = _rigidity_markers(reply)

    return {
        "turn_index": turn_index,
        "message": message,
        "status": status,
        "reply": reply,
        "reply_signals": rigidity,
        "node_sources": {
            "memory": (memory_node or {}).get("source") if isinstance(memory_node, dict) else None,
            "planner": (planner_node or {}).get("source") if isinstance(planner_node, dict) else None,
            "executor": (executor_node or {}).get("source") if isinstance(executor_node, dict) else None,
        },
        "memory_input": memory_input,
        "planner_input": planner_input,
        "planner_output": planner_output,
        "executor_input": executor_input,
        "executor_output": executor_output,
        "planner_recent_dialogue_len": len(planner_input.get("recent_dialogue_short", []) if isinstance(planner_input, dict) else []),
        "executor_recent_dialogue_len": len(executor_input.get("recent_dialogue_short", []) if isinstance(executor_input, dict) else []),
        "selected_memory_count": len(planner_input.get("selected_memory", []) if isinstance(planner_input, dict) else []),
    }


def _run_surface_sequence(client: TestClient, *, surface: str, user_id: str, session_id: str, messages: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for turn_index, message in enumerate(messages, start=1):
        if surface == "optimizador":
            resp = client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "forensics-humanity-live-progressive",
                    "user_id": user_id,
                    "session_id": session_id,
                    "message": message,
                    "conversation_id": None,
                    "scope_turn_id": None,
                    "repeat_from_turn_id": None,
                },
            )
        else:
            resp = client.post(
                "/api/interfaz_usuario/negociacion/turn",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "message": message,
                    "new_conversation": False,
                },
            )
        state = get_session_state(user_id=user_id, session_id=session_id)
        trace = resolve_traces(state)[-1]
        body = resp.json()
        records.append(
            _turn_record(
                trace=trace,
                message=message,
                reply=str(body.get("reply") or ""),
                status=resp.status_code,
                turn_index=turn_index,
            )
        )
    return records


def _scenario_compare(name: str, optimizer_turns: list[dict[str, Any]], interfaz_turns: list[dict[str, Any]]) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    for opt_turn, iu_turn in zip(optimizer_turns, interfaz_turns):
        structural_left = {
            "planner_recent_dialogue_len": opt_turn["planner_recent_dialogue_len"],
            "executor_recent_dialogue_len": opt_turn["executor_recent_dialogue_len"],
            "selected_memory_count": opt_turn["selected_memory_count"],
        }
        structural_right = {
            "planner_recent_dialogue_len": iu_turn["planner_recent_dialogue_len"],
            "executor_recent_dialogue_len": iu_turn["executor_recent_dialogue_len"],
            "selected_memory_count": iu_turn["selected_memory_count"],
        }
        semantic_left = {
            "planner_output": opt_turn.get("planner_output", {}),
            "executor_output": opt_turn.get("executor_output", {}),
        }
        semantic_right = {
            "planner_output": iu_turn.get("planner_output", {}),
            "executor_output": iu_turn.get("executor_output", {}),
        }

        structural_diff = _first_diff(structural_left, structural_right)
        semantic_diff = _first_diff(semantic_left, semantic_right)
        expressive_diff = None if opt_turn.get("reply") == iu_turn.get("reply") else "reply"

        diffs.append(
            {
                "turn_index": opt_turn["turn_index"],
                "structural_first_diff": structural_diff,
                "semantic_first_diff": semantic_diff,
                "expressive_first_diff": expressive_diff,
                "optimizer_rigidity_score": opt_turn["reply_signals"]["rigidity_score"],
                "interfaz_rigidity_score": iu_turn["reply_signals"]["rigidity_score"],
                "rigidity_gap_interfaz_minus_optimizer": iu_turn["reply_signals"]["rigidity_score"] - opt_turn["reply_signals"]["rigidity_score"],
            }
        )

    first_structural = next((d for d in diffs if d["structural_first_diff"] is not None), None)
    first_semantic = next((d for d in diffs if d["semantic_first_diff"] is not None), None)
    first_expressive = next((d for d in diffs if d["expressive_first_diff"] is not None), None)
    positive_gap_turns = [d["turn_index"] for d in diffs if d["rigidity_gap_interfaz_minus_optimizer"] > 0]

    return {
        "name": name,
        "optimizer": optimizer_turns,
        "interfaz_usuario": interfaz_turns,
        "per_turn_diff": diffs,
        "checks": {
            "first_structural_diff": first_structural,
            "first_semantic_diff": first_semantic,
            "first_expressive_diff": first_expressive,
            "positive_rigidity_gap_turns": positive_gap_turns,
        },
    }


def _seed_residual(client: TestClient, *, user_id: str, session_id: str, turns: list[str]) -> None:
    for message in turns:
        client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "new_conversation": False,
            },
        )


def _with_ablation_recent_window(size: int):
    original_planner = flow_config.build_planner_input
    original_executor = flow_config.build_executor_input

    def patched_planner(*args: Any, **kwargs: Any):
        payload = original_planner(*args, **kwargs)
        payload.recent_dialogue_short = payload.recent_dialogue_short[-size:]
        return payload

    def patched_executor(*args: Any, **kwargs: Any):
        payload = original_executor(*args, **kwargs)
        payload.recent_dialogue_short = payload.recent_dialogue_short[-(size * 2):]
        return payload

    return patch.multiple(
        flow_config,
        build_planner_input=patched_planner,
        build_executor_input=patched_executor,
    )


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    client = TestClient(app)

    runtime_mode = "openai_live" if os.getenv("OPENAI_API_KEY") else "fallback_no_api_key"

    measured_messages = [
        "Gracias por el avance. ¿podemos cerrar precio hoy?",
        "Te propongo 7000 con garantía completa.",
        "Si te parece razonable, lo dejamos listo ahora.",
        "Necesito una respuesta clara para avanzar.",
        "Puedo ajustar condiciones si cerramos hoy.",
        "Si confirmas, pasamos a siguiente paso.",
        "Prefiero que quede simple y claro para ambos.",
        "¿Lo cerramos en esos términos?",
    ]
    residual_messages = [
        "Confirmo recepción de tu oferta previa.",
        "Procedamos a revisar cláusulas y formalización.",
        "Mi oferta es mantener la estructura contractual.",
        "Necesito confirmación administrativa para continuar.",
        "Podemos dejar acta de los términos acordados.",
    ]

    scenario_a = _scenario_compare(
        "A_baseline_clean_controlled",
        _run_surface_sequence(client, surface="optimizador", user_id="u_a_opt", session_id="s_a_opt", messages=measured_messages),
        _run_surface_sequence(client, surface="interfaz_usuario", user_id="u_a_iu", session_id="s_a_iu", messages=measured_messages),
    )

    scenario_b = _scenario_compare(
        "B_progressive_live_continuous",
        _run_surface_sequence(client, surface="optimizador", user_id="u_b_opt", session_id="s_b_opt", messages=measured_messages + measured_messages[:4]),
        _run_surface_sequence(client, surface="interfaz_usuario", user_id="u_b_iu", session_id="s_b_iu", messages=measured_messages + measured_messages[:4]),
    )

    _seed_residual(client, user_id="u_c_iu", session_id="s_c_iu", turns=residual_messages)
    scenario_c = _scenario_compare(
        "C_controlled_asymmetric_continuity",
        _run_surface_sequence(client, surface="optimizador", user_id="u_c_opt", session_id="s_c_opt", messages=measured_messages),
        _run_surface_sequence(client, surface="interfaz_usuario", user_id="u_c_iu", session_id="s_c_iu", messages=measured_messages),
    )

    with _with_ablation_recent_window(size=4):
        _seed_residual(client, user_id="u_d_iu", session_id="s_d_iu", turns=residual_messages)
        scenario_d = _scenario_compare(
            "D_targeted_ablation_recent_window",
            _run_surface_sequence(client, surface="optimizador", user_id="u_d_opt", session_id="s_d_opt", messages=measured_messages),
            _run_surface_sequence(client, surface="interfaz_usuario", user_id="u_d_iu", session_id="s_d_iu", messages=measured_messages),
        )

    report = {
        "report_name": "forensics_humanity_live_progressive_residual",
        "runtime_mode": runtime_mode,
        "notes": {
            "live_runtime_attempted": True,
            "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "limitation": None if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY ausente: el runtime ejecuta fallback; la evidencia semántica/expresiva queda limitada.",
        },
        "scenarios": [scenario_a, scenario_b, scenario_c, scenario_d],
        "checks": {
            "A_first_structural_diff": scenario_a["checks"]["first_structural_diff"],
            "B_first_structural_diff": scenario_b["checks"]["first_structural_diff"],
            "C_first_structural_diff": scenario_c["checks"]["first_structural_diff"],
            "C_first_semantic_diff": scenario_c["checks"]["first_semantic_diff"],
            "C_first_expressive_diff": scenario_c["checks"]["first_expressive_diff"],
            "C_positive_rigidity_gap_turns": scenario_c["checks"]["positive_rigidity_gap_turns"],
            "D_positive_rigidity_gap_turns": scenario_d["checks"]["positive_rigidity_gap_turns"],
        },
    }
    return deepcopy(report)


def main() -> None:
    report = build_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {REPORT_PATH}")


if __name__ == "__main__":
    main()
