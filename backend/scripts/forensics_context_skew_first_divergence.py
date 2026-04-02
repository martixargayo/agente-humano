from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import bind_context_to_session, read_bound_context_from_session, resolve_context_for_prompts_dir, resolve_negotiation_context
from negociacion.orchestration import flow_config, turn_contract
from negociacion.orchestration.turn_execution_context import TurnExecutionContext
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult
from sessions.state import SessionState

REPORT_PATH = ROOT.parent / "docs" / "forensics_context_skew_first_divergence_report.json"


def _now() -> int:
    return time.perf_counter_ns()


def _context_from_prompts_dir(prompts_dir: str | None) -> str | None:
    if not prompts_dir:
        return None
    resolved = resolve_context_for_prompts_dir(Path(prompts_dir))
    return resolved.context_id if resolved is not None else None


def _context_from_persona(policy: dict[str, Any] | None) -> str | None:
    canon = json.dumps(policy or {}, ensure_ascii=False, sort_keys=True)
    for context_id, hashes in _PERSONA_FP.items():
        if canon in hashes:
            return context_id
    return None


def _persona_fingerprints() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for context_id in ["baseline_current", "validacion_multicontexto", "sala_reuniones"]:
        resolved = resolve_negotiation_context(context_id)
        raw = json.loads(resolved.persona_path.read_text(encoding="utf-8"))
        hashes: set[str] = set()
        if isinstance(raw, dict):
            for key in ["policy", "expressive"]:
                section = raw.get(key)
                if isinstance(section, dict):
                    hashes.add(json.dumps(section, ensure_ascii=False, sort_keys=True))
        out[context_id] = hashes
    return out


_PERSONA_FP = _persona_fingerprints()


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
        parsed = {
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": "ok",
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


def _run_scenario(*, scenario_id: str, requested_context_id: str, bound_context_id: str | None) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    state = SessionState(user_id=f"u_{scenario_id}", session_id=f"s_{scenario_id}")
    if bound_context_id is not None:
        bind_context_to_session(state=state, context=resolve_negotiation_context(bound_context_id))

    config = build_negotiation_pipeline_config(context_id=requested_context_id, stateful=True)
    requested_prompts_context = _context_from_prompts_dir(config.prompts_dir)

    original_load_state = flow_config.StateRepository.load_state
    original_build_phase = flow_config.build_phase_input
    original_build_planner = flow_config.build_planner_input
    original_build_executor = flow_config.build_executor_input
    original_build_trace_meta = turn_contract.build_trace_context_meta

    def _record(step: str, **values: Any) -> None:
        events.append({"ts": _now(), "step": step, **values})

    def _patched_load_state(self: flow_config.StateRepository, session_state: SessionState, thread_mode: Any):
        bound = read_bound_context_from_session(session_state)
        _record(
            "load_state.before",
            requested_context_id=requested_context_id,
            requested_prompts_context=requested_prompts_context,
            session_bound_context_id=bound.context_id if bound else None,
        )
        canonical = original_load_state(self, session_state, thread_mode)
        persona_ctx = _context_from_persona(canonical.persona.policy.model_dump(mode="json"))
        _record(
            "load_state.after",
            persona_context_id=persona_ctx,
            session_bound_context_id=bound.context_id if bound else None,
        )
        return canonical

    def _patched_build_phase(canonical_state: Any, recent_dialogue: Any, user_turn: Any, trace_meta: Any, prompts_dir: str):
        _record(
            "build_phase_input",
            phase_classifier_card_source_context_id=_context_from_prompts_dir(prompts_dir),
            session_bound_context_id=(read_bound_context_from_session(state).context_id if read_bound_context_from_session(state) else None),
        )
        return original_build_phase(canonical_state, recent_dialogue, user_turn, trace_meta, prompts_dir)

    def _patched_build_planner(canonical_state: Any, recent_dialogue: Any, user_turn: Any, trace_meta: Any, prompts_dir: str):
        persona_ctx = _context_from_persona(canonical_state.persona.policy.model_dump(mode="json"))
        _record(
            "build_planner_input",
            persona_source_context_id=persona_ctx,
            phase_card_source_context_id=_context_from_prompts_dir(prompts_dir),
            session_bound_context_id=(read_bound_context_from_session(state).context_id if read_bound_context_from_session(state) else None),
        )
        return original_build_planner(canonical_state, recent_dialogue, user_turn, trace_meta, prompts_dir)

    def _patched_build_executor(canonical_state: Any, recent_dialogue: Any, planner_output: Any, user_turn: Any, trace_meta: Any, max_recent_turns: int, prompts_dir: str):
        persona_ctx = _context_from_persona(canonical_state.persona.expressive.model_dump(mode="json"))
        _record(
            "build_executor_input",
            persona_source_context_id=persona_ctx,
            phase_card_source_context_id=_context_from_prompts_dir(prompts_dir),
            session_bound_context_id=(read_bound_context_from_session(state).context_id if read_bound_context_from_session(state) else None),
        )
        return original_build_executor(canonical_state, recent_dialogue, planner_output, user_turn, trace_meta, max_recent_turns, prompts_dir)

    def _patched_trace_context_meta(*, state: SessionState, overrides_applied: bool = False, **kwargs: Any):
        meta = original_build_trace_meta(state=state, overrides_applied=overrides_applied, **kwargs)
        _record("build_trace_context_meta", trace_context_id=meta.context_id)
        return meta

    with (
        patch("negociacion.orchestration.flow_config.StateRepository.load_state", _patched_load_state),
        patch("negociacion.orchestration.flow_config.build_phase_input", _patched_build_phase),
        patch("negociacion.orchestration.flow_config.build_planner_input", _patched_build_planner),
        patch("negociacion.orchestration.flow_config.build_executor_input", _patched_build_executor),
        patch("negociacion.orchestration.turn_contract.build_trace_context_meta", _patched_trace_context_meta),
        patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured),
    ):
        turn_context = TurnExecutionContext(
            user_id=state.user_id,
            session_id=state.session_id,
            execution_mode="stateful",
            effective_context_id=requested_context_id,
            requested_context_id=requested_context_id,
            session_bound_context_id=bound_context_id,
            context_source="internal_explicit",
            entry_surface="forensics",
            entrypoint="forensics_context_skew_first_divergence",
        )
        blocked: dict[str, Any] | None = None
        try:
            execute_turn_with_contract(
                state=state,
                user_message="hola",
                config=config,
                contract=TurnEntryContract(
                    entry_surface="forensics",
                    entrypoint="forensics_context_skew_first_divergence",
                    overrides_applied=False,
                    optimizer_wrapper_used=False,
                ),
                turn_context=turn_context,
            )
        except Exception as exc:
            blocked = {"blocked": True, "error": type(exc).__name__}

    mismatches: list[dict[str, Any]] = []
    for event in events:
        if event.get("session_bound_context_id") and event.get("requested_context_id"):
            if event["session_bound_context_id"] != event["requested_context_id"]:
                mismatches.append(event)
                continue
        if event.get("persona_source_context_id") and event.get("phase_card_source_context_id"):
            if event["persona_source_context_id"] != event["phase_card_source_context_id"]:
                mismatches.append(event)
                continue
        if event.get("trace_context_id") and requested_context_id != event.get("trace_context_id"):
            mismatches.append(event)
            continue

    first_mismatch = mismatches[0] if mismatches else None

    return {
        "scenario_id": scenario_id,
        "requested_context_id": requested_context_id,
        "bound_context_id": bound_context_id,
        "requested_prompts_context": requested_prompts_context,
        "events": events,
        "first_mismatch": first_mismatch,
        "blocked": blocked,
    }


def build_report() -> dict[str, Any]:
    scenarios = [
        _run_scenario(
            scenario_id="clean_validacion",
            requested_context_id="validacion_multicontexto",
            bound_context_id="validacion_multicontexto",
        ),
        _run_scenario(
            scenario_id="clean_sala",
            requested_context_id="sala_reuniones",
            bound_context_id="sala_reuniones",
        ),
        _run_scenario(
            scenario_id="forced_skew_validacion_to_sala",
            requested_context_id="sala_reuniones",
            bound_context_id="validacion_multicontexto",
        ),
        _run_scenario(
            scenario_id="forced_skew_sala_to_validacion",
            requested_context_id="validacion_multicontexto",
            bound_context_id="sala_reuniones",
        ),
    ]
    return {"report_version": "context_skew_first_divergence.v1", "scenarios": scenarios}


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
