from __future__ import annotations

import logging
import time

from ..executor import normalize_executor_output, render_executor_output
from ..llm_planning_context import build_full_roleplay_profiles
from ..phase_map import get_phase_map_v1
from ..schemas import (
    default_constraints_struct,
    default_policy_decision,
    default_progress_state,
)
from ..state.deps import DEFAULT_DEPS, get_last_execute_meta
from ..telemetry.trace_runtime import record_llm_call

logger = logging.getLogger(__name__)


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def executor_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    user_message = state.get("user_message") or ""
    policy_decision = state.get("policy_decision") or default_policy_decision()

    state["executed_policy"] = state.get("executed_policy") or policy_decision
    executed = state["executed_policy"] or default_policy_decision()

    policy_id = executed.get("policy_id", "semantic_ledger")
    progress_state = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else default_progress_state()

    persona_profile, scene_profile, style_contract, constraints_profile = build_full_roleplay_profiles(progress_state)
    constraints_struct = (
        progress_state.get("render_constraints_struct")
        if isinstance(progress_state.get("render_constraints_struct"), dict)
        else constraints_profile
    )
    state["phase_map_json"] = state.get("phase_map_json") if isinstance(state.get("phase_map_json"), dict) else get_phase_map_v1()

    llm_started = time.perf_counter()
    executor_output = render_executor_output(
        state,
        deps=deps,
        conversation_mode=str(progress_state.get("conversation_mode", "general") or "general"),
        policy_pack_active="semantic",
        policy_id=policy_id,
        persona_profile=persona_profile,
        scene_profile=scene_profile,
        style_contract=style_contract,
        constraints_struct=constraints_struct if isinstance(constraints_struct, dict) else default_constraints_struct(),
        strategy_summary={},
        memory_block="",
        world_state=state.get("world_state", {}),
        user_message=user_message,
    )
    execute_meta = get_last_execute_meta()
    record_llm_call(
        state,
        name="executor_llm",
        node="executor",
        started=llm_started,
        ok=True,
        model=execute_meta.get("model"),
        tokens_in=execute_meta.get("tokens_in"),
        tokens_out=execute_meta.get("tokens_out"),
        retry_count=int(execute_meta.get("retry_count", 0) or 0),
        error_stage=str(execute_meta.get("error_stage", "")),
        error=str(execute_meta.get("error", "")),
        input_prompt_rendered=str(execute_meta.get("input_prompt_rendered", "")),
        output_text_rendered=str(execute_meta.get("output_text_rendered", "")),
        input_payload_raw=execute_meta.get("rendered_messages"),
        output_payload_raw=executor_output,
    )

    executor_output = normalize_executor_output(executor_output)
    state["executor_output"] = executor_output
    state["assistant_message"] = executor_output.get("response_text", "")
    state["response"] = state["assistant_message"]
    state["progress_state"] = progress_state

    planner_hash = str(state.get("planner_ledger_hash", "") or "")
    executor_hash = str(state.get("executor_ledger_hash", "") or "")
    effective_hash = str(state.get("effective_ledger_hash", "") or "")
    state["ledger_observability"] = {
        "planner_ledger_hash": planner_hash,
        "executor_ledger_hash": executor_hash,
        "effective_ledger_hash": effective_hash,
        "ledger_mismatch_detected": bool(planner_hash and executor_hash and planner_hash != executor_hash),
    }

    state["executor_debug_v2"] = {
        "output_meta": {
            "response_length": len(state.get("assistant_message", "")),
        },
    }
    return state
