from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from interfaz_usuario import services as interfaz_services
from negociacion import pipeline as negotiation_pipeline
from negociacion.contexts import bind_context_to_session, read_bound_context_from_session, resolve_context_for_prompts_dir, resolve_negotiation_context
from negociacion.optimizador import services as optimizer_services
from negociacion.orchestration import flow_config, turn_contract
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SessionState, get_session_store

REPORT_PATH = ROOT.parent / "docs" / "forensics_runtime_broken_route_map_report.json"


def _now() -> int:
    return time.perf_counter_ns()


def _ctx_from_prompts(prompts_dir: str | None) -> str | None:
    if not prompts_dir:
        return None
    resolved = resolve_context_for_prompts_dir(Path(prompts_dir))
    return resolved.context_id if resolved is not None else None


def _persona_fingerprints() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for context_id in ["baseline_current", "validacion_multicontexto", "sala_reuniones"]:
        resolved = resolve_negotiation_context(context_id)
        raw = json.loads(resolved.persona_path.read_text(encoding="utf-8"))
        hashes = {
            json.dumps(raw.get("policy", {}), ensure_ascii=False, sort_keys=True),
            json.dumps(raw.get("expressive", {}), ensure_ascii=False, sort_keys=True),
        }
        out[context_id] = hashes
    return out


_PERSONA_FP = _persona_fingerprints()


def _ctx_from_persona(data: dict[str, Any]) -> str | None:
    canon = json.dumps(data, ensure_ascii=False, sort_keys=True)
    for context_id, fps in _PERSONA_FP.items():
        if canon in fps:
            return context_id
    return None


def _fake_call_structured(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    node_name: str,
    prompt_io_adapter: Any,
    response_model: type[Any],
    reasoning_effort: str,
    request_context: dict[str, str],
    store: bool,
) -> StructuredCallResult:
    _ = (client, model, messages, node_name, prompt_io_adapter, reasoning_effort, request_context, store)
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
            "limits": {
                "max_sentences": 2,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
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


def _instrumented_call(route_id: str, run_fn: Callable[[SessionState], dict[str, Any]], *, state: SessionState) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    orig_load_state = flow_config.StateRepository.load_state
    orig_build_planner = flow_config.build_planner_input
    orig_build_executor = flow_config.build_executor_input
    orig_trace_meta = turn_contract.build_trace_context_meta

    def rec(step: str, **values: Any) -> None:
        events.append({"ts": _now(), "step": step, **values})

    def patched_load_state(self: flow_config.StateRepository, session_state: SessionState, thread_mode: Any):
        bound = read_bound_context_from_session(session_state)
        rec("load_state.before", session_bound_context_id=bound.context_id if bound else None)
        canonical = orig_load_state(self, session_state, thread_mode)
        rec("load_state.after", persona_context_id=_ctx_from_persona(canonical.persona.policy.model_dump(mode="json")))
        return canonical

    def patched_build_planner(canonical_state: Any, recent_dialogue: Any, user_turn: Any, trace_meta: Any, prompts_dir: str):
        rec(
            "build_planner_input",
            persona_source_context_id=_ctx_from_persona(canonical_state.persona.policy.model_dump(mode="json")),
            phase_card_source_context_id=_ctx_from_prompts(prompts_dir),
        )
        return orig_build_planner(canonical_state, recent_dialogue, user_turn, trace_meta, prompts_dir)

    def patched_build_executor(canonical_state: Any, recent_dialogue: Any, planner_output: Any, user_turn: Any, trace_meta: Any, max_recent_turns: int, prompts_dir: str):
        rec(
            "build_executor_input",
            persona_source_context_id=_ctx_from_persona(canonical_state.persona.expressive.model_dump(mode="json")),
            phase_card_source_context_id=_ctx_from_prompts(prompts_dir),
        )
        return orig_build_executor(canonical_state, recent_dialogue, planner_output, user_turn, trace_meta, max_recent_turns, prompts_dir)

    def patched_trace_meta(*, state: SessionState, overrides_applied: bool = False, **kwargs: Any):
        meta = orig_trace_meta(state=state, overrides_applied=overrides_applied, **kwargs)
        rec("build_trace_context_meta", trace_context_id=meta.context_id)
        return meta

    with (
        patch("negociacion.orchestration.flow_config.StateRepository.load_state", patched_load_state),
        patch("negociacion.orchestration.flow_config.build_planner_input", patched_build_planner),
        patch("negociacion.orchestration.flow_config.build_executor_input", patched_build_executor),
        patch("negociacion.orchestration.turn_contract.build_trace_context_meta", patched_trace_meta),
        patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured),
    ):
        result = run_fn(state)

    return {"route_id": route_id, "events": events, "result": result}


def _route_direct_execute_turn_contract_mismatch(state: SessionState) -> dict[str, Any]:
    bind_context_to_session(state=state, context=resolve_negotiation_context("validacion_multicontexto"))
    config = build_negotiation_pipeline_config(context_id="sala_reuniones", stateful=True)
    try:
        execute_turn_with_contract(
            state=state,
            user_message="hola",
            config=config,
            contract=TurnEntryContract(
                entry_surface="forensics",
                entrypoint="direct_execute_turn_contract",
                overrides_applied=False,
                optimizer_wrapper_used=False,
            ),
        )
        return {"requested_context_id": "sala_reuniones", "bound_context_id": "validacion_multicontexto", "admitted": True}
    except Exception as exc:
        return {
            "requested_context_id": "sala_reuniones",
            "bound_context_id": "validacion_multicontexto",
            "admitted": False,
            "status": 400,
            "error": type(exc).__name__,
            "blocked_stage": "pre_execution",
        }


def _route_pipeline_run_negotiation_agent_default(state: SessionState) -> dict[str, Any]:
    bind_context_to_session(state=state, context=resolve_negotiation_context("sala_reuniones"))
    try:
        negotiation_pipeline.run_negotiation_agent(state, "hola")
        return {"requested_context_id": "baseline_current (implicit)", "bound_context_id": "sala_reuniones", "admitted": True}
    except Exception as exc:
        return {
            "requested_context_id": "baseline_current (implicit)",
            "bound_context_id": "sala_reuniones",
            "admitted": False,
            "status": 400,
            "error": type(exc).__name__,
        }


def _route_interfaz_conflict_guardrail(state: SessionState) -> dict[str, Any]:
    _ = state
    interfaz_services.ensure_session(user_id="u_route_iu", session_id="s_route_iu", context_id="validacion_multicontexto")
    try:
        interfaz_services.ensure_session(user_id="u_route_iu", session_id="s_route_iu", context_id="sala_reuniones")
        return {"admitted": True, "status": 200}
    except HTTPException as exc:
        return {"admitted": False, "status": exc.status_code, "error": str(exc.detail)}


def _route_optimizer_conflict_guardrail(state: SessionState) -> dict[str, Any]:
    _ = state
    optimizer_services.ensure_session(user_id="u_route_opt", session_id="s_route_opt", context_id="validacion_multicontexto")
    try:
        optimizer_services.ensure_session(user_id="u_route_opt", session_id="s_route_opt", context_id="sala_reuniones")
        return {"admitted": True, "status": 200}
    except HTTPException as exc:
        return {"admitted": False, "status": exc.status_code, "error": str(exc.detail)}




def _route_api_negociar_legacy_endpoint(state: SessionState) -> dict[str, Any]:
    bind_context_to_session(state=state, context=resolve_negotiation_context("sala_reuniones"))
    get_session_store().save(state)
    client = TestClient(app)
    response = client.post("/negociar", json={"user_id": state.user_id, "session_id": state.session_id, "message": "hola"})
    return {"admitted": response.status_code == 200, "status": response.status_code, "response": response.json()}

def _classify_first_mismatch(events: list[dict[str, Any]], requested: str, bound: str) -> dict[str, Any] | None:
    for event in events:
        if event.get("step") == "load_state.before":
            if event.get("session_bound_context_id") and event.get("session_bound_context_id") != requested:
                return event
        if event.get("step") in {"build_planner_input", "build_executor_input"}:
            if event.get("persona_source_context_id") != event.get("phase_card_source_context_id"):
                return event
        if event.get("step") == "build_trace_context_meta":
            if event.get("trace_context_id") != requested:
                return event
    return None




def _static_entrypoint_inventory() -> dict[str, list[dict[str, Any]]]:
    root = ROOT
    execute_callers: list[dict[str, Any]] = []
    run_callers: list[dict[str, Any]] = []
    negotiation_agent_callers: list[dict[str, Any]] = []
    for path in root.rglob('*.py'):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in {'tests', 'scripts'}:
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            if 'execute_turn_with_contract(' in line and 'def execute_turn_with_contract' not in line:
                execute_callers.append({'file': str(rel), 'line': lineno, 'code': line.strip()})
            if 'run_negotiation_cognitive_turn(' in line and 'def run_negotiation_cognitive_turn' not in line:
                run_callers.append({'file': str(rel), 'line': lineno, 'code': line.strip()})
            if 'run_negotiation_agent(' in line and 'def run_negotiation_agent' not in line:
                negotiation_agent_callers.append({'file': str(rel), 'line': lineno, 'code': line.strip()})
    return {'execute_turn_with_contract_callers': execute_callers, 'run_negotiation_cognitive_turn_callers': run_callers, 'run_negotiation_agent_callers': negotiation_agent_callers}
def build_report() -> dict[str, Any]:
    routes: list[dict[str, Any]] = []

    # Guarded route 1: direct execute_turn_with_contract mismatch blocked pre-execution.
    out1 = _instrumented_call(
        "direct_execute_turn_contract",
        _route_direct_execute_turn_contract_mismatch,
        state=SessionState(user_id="u_r1", session_id="s_r1"),
    )
    out1["first_mismatch"] = _classify_first_mismatch(out1["events"], "sala_reuniones", "validacion_multicontexto")
    routes.append(out1)

    # Broken route 2: pipeline default baseline while bound context differs.
    out2 = _instrumented_call(
        "pipeline_run_negotiation_agent_default",
        _route_pipeline_run_negotiation_agent_default,
        state=SessionState(user_id="u_r2", session_id="s_r2"),
    )
    out2["first_mismatch"] = _classify_first_mismatch(out2["events"], "baseline_current", "sala_reuniones")
    routes.append(out2)

    # Broken route 3: legacy /negociar endpoint -> run_negotiation_agent
    out_legacy = _instrumented_call(
        "api_negociar_legacy_endpoint",
        _route_api_negociar_legacy_endpoint,
        state=SessionState(user_id="u_rlegacy", session_id="s_rlegacy"),
    )
    out_legacy["first_mismatch"] = _classify_first_mismatch(out_legacy["events"], "baseline_current", "sala_reuniones")
    routes.append(out_legacy)

    # Guarded route 1: interfaz ensures 409 conflict.
    out3 = _instrumented_call(
        "interfaz_ensure_session_conflict",
        _route_interfaz_conflict_guardrail,
        state=SessionState(user_id="u_r3", session_id="s_r3"),
    )
    routes.append(out3)

    # Guarded route 2: optimizer ensures 409 conflict.
    out4 = _instrumented_call(
        "optimizer_ensure_session_conflict",
        _route_optimizer_conflict_guardrail,
        state=SessionState(user_id="u_r4", session_id="s_r4"),
    )
    routes.append(out4)

    return {"report_version": "runtime_broken_route_map.v1", "routes": routes, "static_inventory": _static_entrypoint_inventory()}


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
