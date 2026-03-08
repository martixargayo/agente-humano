from __future__ import annotations

from contextlib import contextmanager

from sessions.state import SessionState

from ..cases import load_jsonl_cases
from ..graders.end_to_end import grade_end_to_end_case
from . import print_summary, summarize_results
from ...orchestration import flow_config as fc
from ...orchestration.flow_config import StructuredCallResult, build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from ...state.canonical_state import build_default_canonical_state
from ...state.shared_types import StructuredCallSource


@contextmanager
def _patched_structured_calls(mock_outputs: dict):
    original_build_client = fc._build_client
    original_refresh = fc.refresh_request_context
    original_exec_memory_phase = fc._execute_memory_and_phase
    original_call_structured = fc._call_structured

    def _fake_build_client():
        return object()

    def _fake_refresh_request_context(client, canonical_state, mode_default):
        _ = (client, canonical_state, mode_default)
        return {"conversation": "eval-conversation"}

    def _fake_execute_memory_and_phase(**kwargs):
        _ = kwargs
        mem_call = StructuredCallResult(
            parsed_json=mock_outputs["memory"],
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
        )
        phase_call = StructuredCallResult(
            parsed_json=mock_outputs["phase_classifier"],
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
        )
        return mem_call, 1, phase_call, 1, {"conversation": "eval-conversation"}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, request_context, store)
        node_name = "planner" if response_model.__name__ == "PlannerOutput" else "executor"
        return StructuredCallResult(
            parsed_json=mock_outputs[node_name],
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
        )

    fc._build_client = _fake_build_client
    fc.refresh_request_context = _fake_refresh_request_context
    fc._execute_memory_and_phase = _fake_execute_memory_and_phase
    fc._call_structured = _fake_call_structured
    try:
        yield
    finally:
        fc._build_client = original_build_client
        fc.refresh_request_context = original_refresh
        fc._execute_memory_and_phase = original_exec_memory_phase
        fc._call_structured = original_call_structured


def run() -> int:
    cases = load_jsonl_cases("end_to_end_mock_cases.jsonl")
    results = []
    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False, "feature_traces": True})

    for case in cases:
        init = case.get("initial_state", {})
        session = SessionState(user_id=init.get("user_id", "eval_user"), session_id=init.get("session_id", case["case_id"]))
        session.history.extend(case.get("recent_dialogue", []))
        session.world_state[config.memory_key] = build_default_canonical_state(
            session_id=session.session_id,
            user_id=session.user_id,
            thread_mode=config.thread_mode_default,
        ).model_dump(mode="json")

        with _patched_structured_calls(case["mock_outputs"]):
            reply, updated = run_negotiation_cognitive_turn(session, case["user_message"], config)

        result = grade_end_to_end_case(
            case_id=case["case_id"],
            final_reply=reply,
            world_state=updated.world_state,
            memory_key=config.memory_key,
            expected_checks=case.get("expected_checks", {}),
        )
        results.append(result)

    summary = summarize_results("end_to_end_mock", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
