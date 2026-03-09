from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sessions.state import SessionState

from ...nodes.memory_node import DialogueMessage, TraceMeta
from ...nodes.phase_classifier_node import PhaseClassifierOutput
from ...nodes.planner_node import PlannerOutput
from ...nodes.executor_node import ExecutorOutput
from ...orchestration import flow_config as fc
from ...orchestration.flow_config import (
    StructuredCallResult,
    _build_user_turn,
    _call_structured,
    _memory_fallback,
    _phase_classifier_fallback,
    _planner_fallback,
    _executor_fallback,
    apply_memory_output_to_state,
    apply_phase_classifier_output_to_state,
    apply_planner_output_to_state,
    build_memory_input,
    build_memory_messages,
    build_phase_classifier_messages_payload,
    build_phase_input,
    build_planner_input,
    build_planner_messages,
    build_executor_input,
    build_executor_messages,
    build_negotiation_pipeline_config,
    refresh_request_context,
)
from ...state.canonical_state import CanonicalState, build_default_canonical_state
from ...state.shared_types import StructuredCallSource


def _trace_meta(turn_id: str, prompt_version: str, schema_version: str, model_target: str) -> TraceMeta:
    return TraceMeta(turn_id=turn_id, prompt_version=prompt_version, schema_version=schema_version, model_target=model_target)


def _to_recent_dialogue(items: list[dict]) -> list[DialogueMessage]:
    out: list[DialogueMessage] = []
    for item in items:
        role = item.get("role")
        text = item.get("text") or item.get("content") or ""
        if role in {"assistant", "user"}:
            out.append(DialogueMessage(role=role, text=str(text)))
    return out


def build_live_context(case: dict) -> tuple[SessionState, CanonicalState, list[DialogueMessage], object, object, object, object, object, object, object, object]:
    config = build_negotiation_pipeline_config()
    now_iso = datetime.now(timezone.utc).isoformat()
    init = case.get("initial_state", {})
    session = SessionState(user_id=init.get("user_id", "eval_live_user"), session_id=init.get("session_id", case["case_id"]))
    canonical = build_default_canonical_state(
        session_id=session.session_id,
        user_id=session.user_id,
        thread_mode=config.thread_mode_default,
        now_iso=now_iso,
    )
    recent = _to_recent_dialogue(case.get("recent_dialogue", []))
    user_turn = _build_user_turn(case["user_message"], now_iso)

    prompts_dir = Path(config.prompts_dir)
    memory_prompt = fc._read_text(prompts_dir / "summarizer_prompt.txt", "")
    phase_prompt = fc._read_text(prompts_dir / "phase_classifier_prompt.txt", "")
    planner_prompt = fc._read_text(prompts_dir / "planner_prompt.txt", "")
    executor_prompt = fc._read_text(prompts_dir / "executor_prompt.txt", "")

    client = fc._build_client()
    request_context = refresh_request_context(client, canonical, config.thread_mode_default)
    return session, canonical, recent, user_turn, config, client, request_context, memory_prompt, phase_prompt, planner_prompt, executor_prompt


def run_live_phase(case: dict) -> dict:
    _, canonical, recent, user_turn, config, client, request_context, _, phase_prompt, _, _ = build_live_context(case)
    trace = _trace_meta(case["case_id"], config.prompt_version_phase_classifier, "phase_classifier_input.v1", config.model_phase_classifier)
    phase_input = build_phase_input(canonical, recent, user_turn, trace, config.prompts_dir)
    call = _call_structured(client, config.model_phase_classifier, build_phase_classifier_messages_payload(phase_prompt, phase_input), PhaseClassifierOutput, "low", request_context, config.memory_store)
    output = PhaseClassifierOutput.model_validate(call.parsed_json) if call.source == StructuredCallSource.model and call.parsed_json else _phase_classifier_fallback(canonical.planner_state.current_phase)
    return output.model_dump(mode="json")


def run_live_memory(case: dict) -> dict:
    _, canonical, recent, user_turn, config, client, request_context, memory_prompt, _, _, _ = build_live_context(case)
    trace = _trace_meta(case["case_id"], config.prompt_version_memory, "memory_input.v1", config.model_memory)
    memory_input = build_memory_input(canonical, recent, user_turn, trace)
    call = _call_structured(client, config.model_memory, build_memory_messages(memory_prompt, memory_input), fc.MemoryOutput, "low", request_context, config.memory_store)
    output = fc.MemoryOutput.model_validate(call.parsed_json) if call.source == StructuredCallSource.model and call.parsed_json else _memory_fallback(canonical, case["case_id"])
    return output.model_dump(mode="json")


def run_live_planner(case: dict) -> tuple[dict, dict]:
    _, canonical, recent, user_turn, config, client, request_context, memory_prompt, phase_prompt, planner_prompt, _ = build_live_context(case)

    mem_trace = _trace_meta(case["case_id"], config.prompt_version_memory, "memory_input.v1", config.model_memory)
    memory_input = build_memory_input(canonical, recent, user_turn, mem_trace)
    mem_call = _call_structured(client, config.model_memory, build_memory_messages(memory_prompt, memory_input), fc.MemoryOutput, "low", request_context, config.memory_store)
    memory_output = fc.MemoryOutput.model_validate(mem_call.parsed_json) if mem_call.source == StructuredCallSource.model and mem_call.parsed_json else _memory_fallback(canonical, case["case_id"])
    apply_memory_output_to_state(canonical, memory_output)

    phase_trace = _trace_meta(case["case_id"], config.prompt_version_phase_classifier, "phase_classifier_input.v1", config.model_phase_classifier)
    phase_input = build_phase_input(canonical, recent, user_turn, phase_trace, config.prompts_dir)
    phase_call = _call_structured(client, config.model_phase_classifier, build_phase_classifier_messages_payload(phase_prompt, phase_input), PhaseClassifierOutput, "low", request_context, config.memory_store)
    phase_output = PhaseClassifierOutput.model_validate(phase_call.parsed_json) if phase_call.source == StructuredCallSource.model and phase_call.parsed_json else _phase_classifier_fallback(canonical.planner_state.current_phase)
    apply_phase_classifier_output_to_state(canonical, phase_output)

    planner_trace = _trace_meta(case["case_id"], config.prompt_version_planner, "planner_input.v1", config.model_planner)
    planner_input = build_planner_input(canonical, recent, user_turn, planner_trace, config.prompts_dir)
    planner_call = _call_structured(client, config.model_planner, build_planner_messages(planner_prompt, planner_input), PlannerOutput, config.reasoning_effort_planner, request_context, config.planner_store)
    planner_output = PlannerOutput.model_validate(planner_call.parsed_json) if planner_call.source == StructuredCallSource.model and planner_call.parsed_json else _planner_fallback()
    return planner_input.model_dump(mode="json"), planner_output.model_dump(mode="json")


def run_live_executor(case: dict) -> tuple[dict, str, dict]:
    _, canonical, recent, user_turn, config, client, request_context, memory_prompt, phase_prompt, planner_prompt, executor_prompt = build_live_context(case)

    mem_trace = _trace_meta(case["case_id"], config.prompt_version_memory, "memory_input.v1", config.model_memory)
    memory_input = build_memory_input(canonical, recent, user_turn, mem_trace)
    mem_call = _call_structured(client, config.model_memory, build_memory_messages(memory_prompt, memory_input), fc.MemoryOutput, "low", request_context, config.memory_store)
    memory_output = fc.MemoryOutput.model_validate(mem_call.parsed_json) if mem_call.source == StructuredCallSource.model and mem_call.parsed_json else _memory_fallback(canonical, case["case_id"])
    apply_memory_output_to_state(canonical, memory_output)

    phase_trace = _trace_meta(case["case_id"], config.prompt_version_phase_classifier, "phase_classifier_input.v1", config.model_phase_classifier)
    phase_input = build_phase_input(canonical, recent, user_turn, phase_trace, config.prompts_dir)
    phase_call = _call_structured(client, config.model_phase_classifier, build_phase_classifier_messages_payload(phase_prompt, phase_input), PhaseClassifierOutput, "low", request_context, config.memory_store)
    phase_output = PhaseClassifierOutput.model_validate(phase_call.parsed_json) if phase_call.source == StructuredCallSource.model and phase_call.parsed_json else _phase_classifier_fallback(canonical.planner_state.current_phase)
    apply_phase_classifier_output_to_state(canonical, phase_output)

    planner_trace = _trace_meta(case["case_id"], config.prompt_version_planner, "planner_input.v1", config.model_planner)
    planner_input = build_planner_input(canonical, recent, user_turn, planner_trace, config.prompts_dir)
    planner_call = _call_structured(client, config.model_planner, build_planner_messages(planner_prompt, planner_input), PlannerOutput, config.reasoning_effort_planner, request_context, config.planner_store)
    planner_output = PlannerOutput.model_validate(planner_call.parsed_json) if planner_call.source == StructuredCallSource.model and planner_call.parsed_json else _planner_fallback()
    apply_planner_output_to_state(canonical, planner_output)

    executor_trace = _trace_meta(case["case_id"], config.prompt_version_executor, "executor_input.v1", config.model_executor)
    executor_input = build_executor_input(canonical, recent, planner_output, user_turn, executor_trace, config.max_executor_recent_turns, config.prompts_dir)
    executor_call = _call_structured(client, config.model_executor, build_executor_messages(executor_prompt, executor_input), ExecutorOutput, "low", request_context, config.executor_store)
    executor_output = ExecutorOutput.model_validate(executor_call.parsed_json) if executor_call.source == StructuredCallSource.model and executor_call.parsed_json else _executor_fallback(planner_output)
    return executor_input.model_dump(mode="json"), planner_output.status, executor_output.model_dump(mode="json")
