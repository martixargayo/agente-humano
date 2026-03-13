from __future__ import annotations

import copy
import json
import re
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
from negociacion.optimizador import experiments_bridge
from negociacion.optimizador.storage import resolve_traces
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SESSIONS, get_session_state

ORIGINAL_FREEZE = flow_config.freeze_prompt_artifacts
REPORT_PATH = Path("backend/docs/forensics_effective_context_parity_run.json")


@dataclass
class RecordedCall:
    node: str
    turn_id: str | None
    payload: dict[str, Any]
    request_context: dict[str, str]
    threading_mode_effective: str
    store: bool
    model: str


CALLS: list[RecordedCall] = []
PAYLOAD_QUEUE: dict[str, deque[dict[str, Any]]] = defaultdict(deque)


def _node_name(response_model: type[Any]) -> str:
    return {
        "MemoryOutput": "memory",
        "PhaseClassifierOutput": "phase_classifier",
        "PlannerOutput": "planner",
        "ExecutorOutput": "executor",
    }.get(response_model.__name__, response_model.__name__)


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
    payload = json.loads(frozen.payload_json)
    PAYLOAD_QUEUE[node].append(payload)
    return frozen


def _parse_offer(text: str) -> tuple[float | None, list[str], list[str]]:
    low = text.lower()
    m = re.search(r"(\d{3,5})", low)
    price = float(m.group(1)) if m else None
    extras = [kw for kw in ["garantía", "itv", "ruedas", "transferencia"] if kw in low]
    conditions = [kw for kw in ["hoy", "señal", "reserva", "revisión"] if kw in low]
    return price, extras, conditions


def _memory_output(payload: dict[str, Any]) -> dict[str, Any]:
    user_text = payload.get("user_turn", {}).get("normalized_text", "")
    recent = payload.get("recent_dialogue_short", [])
    prev_topic = payload.get("memory_working_current", {}).get("current_topic")
    current_topic = prev_topic or ("precio" if re.search(r"\d", user_text) else "condiciones")
    price, extras, conditions = _parse_offer(user_text)
    return {
        "schema_version": "memory.v1",
        "episodic_append": [
            {
                "event_type": "important_fact",
                "event_summary": f"turn::{len(recent)}::{user_text[:60]}",
                "turn_id": payload.get("trace_meta", {}).get("turn_id", "unknown"),
            }
        ],
        "working_memory_new": {
            "current_topic": current_topic,
            "pending_question": "confirmar cierre" if "?" in user_text else None,
            "last_turn_summary": f"topic={current_topic};recent={len(recent)};user={user_text[:80]}",
        },
        "negotiation_state": {
            "status": "active" if user_text else "inactive",
            "active_axes": sorted(set((["precio"] if price is not None else []) + extras)),
            "last_offer_self": {
                "summary": f"oferta usuario: {user_text[:80]}" if user_text else None,
                "price_amount": price,
                "currency": "EUR" if price is not None else None,
                "extras": extras,
                "conditions": conditions,
                "is_currently_active": True,
                "source_turn_role": "user",
            }
            if user_text
            else None,
            "last_offer_other": None,
            "tentative_agreement": None,
            "stall_state": {
                "is_hard_stalemate": "último" in user_text.lower(),
                "stalemate_reason": "ultimatum_detected" if "último" in user_text.lower() else None,
                "self_ultimatum_active": False,
                "self_ultimatum_summary": None,
            },
            "blockers": ["falta_garantia"] if "garantía" not in user_text.lower() else [],
            "next_open_loop": "alinear_precio_y_condiciones",
        },
    }


def _phase_output(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("current_user_turn", {}).get("normalized_text", "").lower()
    phase = "propuesta_creativa" if any(k in text for k in ["garant", "itv", "ruedas"]) else "concesiones_y_ajuste_final" if re.search(r"\d", text) else "clima_humano"
    return {"schema_version": "phase_classifier.v1", "current_phase": phase}


def _planner_output(payload: dict[str, Any]) -> dict[str, Any]:
    current_phase = payload.get("current_phase", "clima_humano")
    has_offer = bool((payload.get("negotiation_state") or {}).get("last_offer_self"))
    return {
        "schema_version": "planner.v3",
        "status": "plan",
        "turn_goal": f"avanzar_{current_phase}",
        "decision": "counter" if has_offer else "ask",
        "content_plan": {"must_include": ["responder al usuario", "mover negociación"], "must_avoid": ["inventar hechos"]},
        "limits": {"max_sentences": 3, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
        "memory_targets": [m.get("memory_id") for m in payload.get("selected_memory", [])[:1]],
        "done_criteria": ["paso_tactico_emitido"],
    }


def _executor_output(payload: dict[str, Any]) -> dict[str, Any]:
    goal = (payload.get("planner_output") or {}).get("turn_goal", "avanzar")
    return {
        "schema_version": "executor.v1",
        "status": "deliver",
        "spoken_text": f"Perfecto. {goal}. Propongo un siguiente paso concreto.",
        "memory_used": [m.get("memory_id") for m in payload.get("selected_memory_for_reference", [])],
        "refusal_reason": None,
    }


def _fake_call_structured(client: Any, model: str, messages: list[dict[str, str]], response_model: type[Any], reasoning_effort: str, request_context: dict[str, str], store: bool) -> StructuredCallResult:
    _ = (client, messages, reasoning_effort)
    node = _node_name(response_model)
    payload = PAYLOAD_QUEUE[node].popleft() if PAYLOAD_QUEUE[node] else {}
    turn_id = payload.get("trace_meta", {}).get("turn_id") if isinstance(payload, dict) else None
    mode = "conversation" if request_context.get("conversation") else "previous_response_id" if request_context.get("previous_response_id") else "stateless"
    CALLS.append(RecordedCall(node=node, turn_id=turn_id if isinstance(turn_id, str) else None, payload=copy.deepcopy(payload), request_context=dict(request_context), threading_mode_effective=mode, store=store, model=model))

    parsed = _memory_output(payload) if node == "memory" else _phase_output(payload) if node == "phase_classifier" else _planner_output(payload) if node == "planner" else _executor_output(payload) if node == "executor" else {}
    return StructuredCallResult(parsed_json=parsed, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True, raw_output_text=json.dumps(parsed, ensure_ascii=False))


def _snapshot_state(user_id: str, session_id: str) -> dict[str, Any]:
    state = get_session_state(user_id=user_id, session_id=session_id)
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    recent = state.world_state.get("negotiation_canonical_recent_dialogue", []) if isinstance(state.world_state, dict) else []
    return {
        "planner_state": canonical.get("planner_state") if isinstance(canonical, dict) else None,
        "memory_working": canonical.get("memory_working") if isinstance(canonical, dict) else None,
        "negotiation_state": canonical.get("negotiation_state") if isinstance(canonical, dict) else None,
        "recent_dialogue_short": recent[-8:] if isinstance(recent, list) else [],
    }


def _calls_by_turn(turn_id: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in CALLS:
        if c.turn_id != turn_id:
            continue
        out[c.node] = {"payload": c.payload, "request_context": c.request_context, "threading_mode_effective": c.threading_mode_effective, "store": c.store, "model": c.model}
    return out


def _normalize_payload_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(payload)

    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k == "turn_id":
                    out[k] = "__TURN_ID__"
                elif k == "timestamp_iso":
                    out[k] = "__TS__"
                else:
                    out[k] = scrub(v)
            return out
        if isinstance(obj, list):
            return [scrub(x) for x in obj]
        return obj

    return scrub(data)


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


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    experiments_bridge._OVERRIDE_STORE.clear()
    CALLS.clear()
    PAYLOAD_QUEUE.clear()
    client = TestClient(app)

    msgs = [
        "Busco cerrar hoy si el precio encaja",
        "Puedo pagar 6200 si incluyes garantía de 12 meses",
        "Si no hay garantía, podrías incluir ITV recién pasada?",
        "Vale, último esfuerzo: 6500 con transferencia incluida",
    ]

    with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured), patch("negociacion.orchestration.flow_config.freeze_prompt_artifacts", _patched_freeze_prompt_artifacts):
        seed = get_session_state(user_id="seed_u", session_id="seed_s")
        opt = copy.deepcopy(seed)
        opt.user_id, opt.session_id = "u_opt", "s_opt"
        iu = copy.deepcopy(seed)
        iu.user_id, iu.session_id = "u_iu", "s_iu"
        SESSIONS[("u_opt", "s_opt")] = opt
        SESSIONS[("u_iu", "s_iu")] = iu

        turns = []
        for idx, msg in enumerate(msgs, start=1):
            ro = client.post("/api/optimizador/sandbox/turn", json={"optimizer_session_id": "forensics_clean", "user_id": "u_opt", "session_id": "s_opt", "message": msg, "conversation_id": None, "scope_turn_id": None, "repeat_from_turn_id": None})
            ri = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_iu", "session_id": "s_iu", "message": msg, "new_conversation": False})

            opt_trace = resolve_traces(get_session_state(user_id="u_opt", session_id="s_opt"))[-1]
            iu_trace = resolve_traces(get_session_state(user_id="u_iu", session_id="s_iu"))[-1]
            opt_calls = _calls_by_turn(opt_trace.get("turn_id"))
            iu_calls = _calls_by_turn(iu_trace.get("turn_id"))

            node_cmp = {}
            for node in ["memory", "phase_classifier", "planner", "executor"]:
                op = _normalize_payload_for_compare((opt_calls.get(node) or {}).get("payload", {}))
                ip = _normalize_payload_for_compare((iu_calls.get(node) or {}).get("payload", {}))
                node_cmp[node] = {
                    "payload_equal": op == ip,
                    "first_payload_diff": _first_diff(op, ip),
                    "optimizer_request_context": (opt_calls.get(node) or {}).get("request_context", {}),
                    "interfaz_request_context": (iu_calls.get(node) or {}).get("request_context", {}),
                    "request_context_equal": ((opt_calls.get(node) or {}).get("request_context", {}) == (iu_calls.get(node) or {}).get("request_context", {})),
                    "recent_dialogue_len_optimizer": len(op.get("recent_dialogue_short") or op.get("recent_turns") or []),
                    "recent_dialogue_len_interfaz": len(ip.get("recent_dialogue_short") or ip.get("recent_turns") or []),
                }

            sopt = _snapshot_state("u_opt", "s_opt")
            siu = _snapshot_state("u_iu", "s_iu")
            turns.append(
                {
                    "turn_index": idx,
                    "message": msg,
                    "status_optimizer": ro.status_code,
                    "status_interfaz": ri.status_code,
                    "entry_contract_optimizer": opt_trace.get("_entry_contract"),
                    "entry_contract_interfaz": iu_trace.get("_entry_contract"),
                    "node_comparison": node_cmp,
                    "state_compare": {
                        "memory_working_equal": sopt["memory_working"] == siu["memory_working"],
                        "planner_state_equal": sopt["planner_state"] == siu["planner_state"],
                        "negotiation_state_equal": sopt["negotiation_state"] == siu["negotiation_state"],
                        "recent_dialogue_equal": sopt["recent_dialogue_short"] == siu["recent_dialogue_short"],
                        "memory_working_first_diff": _first_diff(sopt["memory_working"], siu["memory_working"]),
                        "planner_state_first_diff": _first_diff(sopt["planner_state"], siu["planner_state"]),
                        "negotiation_state_first_diff": _first_diff(sopt["negotiation_state"], siu["negotiation_state"]),
                        "recent_dialogue_first_diff": _first_diff(sopt["recent_dialogue_short"], siu["recent_dialogue_short"]),
                    },
                    "optimizer_payloads": {n: (opt_calls.get(n) or {}).get("payload", {}) for n in ["memory", "phase_classifier", "planner", "executor"]},
                    "interfaz_payloads": {n: (iu_calls.get(n) or {}).get("payload", {}) for n in ["memory", "phase_classifier", "planner", "executor"]},
                }
            )

        # hidden continuity skew
        skew_opt = get_session_state(user_id="u_opt_skew", session_id="s_opt_skew")
        _ = get_session_state(user_id="u_iu_skew", session_id="s_iu_skew")
        skew_opt.world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "historial oculto 1"},
            {"role": "assistant", "text": "historial oculto 2"},
            {"role": "user", "text": "historial oculto 3"},
        ]
        r_opt_skew = client.post("/api/optimizador/sandbox/turn", json={"optimizer_session_id": "forensics_clean", "user_id": "u_opt_skew", "session_id": "s_opt_skew", "message": "Oferta limpia 6400 con garantía", "conversation_id": None, "scope_turn_id": None, "repeat_from_turn_id": None})
        r_iu_skew = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_iu_skew", "session_id": "s_iu_skew", "message": "Oferta limpia 6400 con garantía", "new_conversation": False})
        opt_skew_trace = resolve_traces(get_session_state(user_id="u_opt_skew", session_id="s_opt_skew"))[-1]
        iu_skew_trace = resolve_traces(get_session_state(user_id="u_iu_skew", session_id="s_iu_skew"))[-1]
        opt_skew_calls = _calls_by_turn(opt_skew_trace.get("turn_id"))
        iu_skew_calls = _calls_by_turn(iu_skew_trace.get("turn_id"))

        skew_cmp = {}
        for node in ["memory", "phase_classifier", "planner", "executor"]:
            op = _normalize_payload_for_compare((opt_skew_calls.get(node) or {}).get("payload", {}))
            ip = _normalize_payload_for_compare((iu_skew_calls.get(node) or {}).get("payload", {}))
            skew_cmp[node] = {
                "payload_equal": op == ip,
                "first_payload_diff": _first_diff(op, ip),
                "recent_dialogue_len_optimizer": len(op.get("recent_dialogue_short") or op.get("recent_turns") or []),
                "recent_dialogue_len_interfaz": len(ip.get("recent_dialogue_short") or ip.get("recent_turns") or []),
            }

        ri_new = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_iu", "session_id": "s_iu", "message": "arranca limpio", "new_conversation": True})
        ro_new = client.post("/api/optimizador/sandbox/new_conversation", json={"optimizer_session_id": "forensics_clean", "user_id": "u_opt", "session_id": "s_opt"})

    first_div = None
    for t in turns:
        for node in ["memory", "phase_classifier", "planner", "executor"]:
            if not t["node_comparison"][node]["payload_equal"]:
                first_div = {"turn_index": t["turn_index"], "node": node, "path": t["node_comparison"][node]["first_payload_diff"]}
                break
        if first_div:
            break

    return {
        "report_version": "effective_context.v2",
        "settings": {"manual_overrides_used": False, "clone_repeat_used": False, "messages": msgs},
        "turns": turns,
        "first_payload_divergence": first_div,
        "hidden_continuity_skew": {
            "status_optimizer": r_opt_skew.status_code,
            "status_interfaz": r_iu_skew.status_code,
            "node_comparison": skew_cmp,
            "first_divergence": next(({"node": n, "path": v["first_payload_diff"]} for n, v in skew_cmp.items() if not v["payload_equal"]), None),
        },
        "new_conversation": {"interfaz_response": ri_new.json(), "optimizer_new_conversation": ro_new.json()},
        "global_checks": {
            "all_node_payloads_equal": all(t["node_comparison"][n]["payload_equal"] for t in turns for n in ["memory", "phase_classifier", "planner", "executor"]),
            "all_memory_working_equal": all(t["state_compare"]["memory_working_equal"] for t in turns),
            "all_planner_state_equal": all(t["state_compare"]["planner_state_equal"] for t in turns),
            "all_negotiation_state_equal": all(t["state_compare"]["negotiation_state_equal"] for t in turns),
            "all_recent_dialogue_equal": all(t["state_compare"]["recent_dialogue_equal"] for t in turns),
        },
    }


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
