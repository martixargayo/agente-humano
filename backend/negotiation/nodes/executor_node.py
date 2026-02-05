from __future__ import annotations

import logging

from ..context_utils import format_memory_block
from ..elementos.render import resolve_render_profiles
from ..executor import build_strategy_summary, normalize_executor_output, render_executor_output
from ..schemas import default_constraints_struct, default_policy_decision, default_progress_state, default_render_state
from ..state.deps import DEFAULT_DEPS
from ..validator import validate_and_repair

logger = logging.getLogger(__name__)


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def executor_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    _ensure_objective(state)

    long_memory = state.get("long_memory") or ""
    short_memory = state.get("short_memory") or ""
    memory_block = format_memory_block(long_memory, short_memory)
    user_message = state.get("user_message") or ""

    policy_decision = state.get("policy_decision") or default_policy_decision()

    state["executed_policy"] = state.get("executed_policy") or policy_decision
    executed = state["executed_policy"] or default_policy_decision()

    policy_id = executed.get("policy_id", "safe_neutral")
    progress_state = state.get("progress_state") or default_progress_state()
    conversation_mode = progress_state.get("conversation_mode", "general")
    policy_pack_active = progress_state.get("policy_pack_active", "universal")

    render_state = progress_state.get("render_state") or default_render_state()
    persona_profile, scene_profile, style_contract = resolve_render_profiles(render_state)

    strategy_summary = build_strategy_summary(
        state, conversation_mode, policy_pack_active, policy_id
    )
    state["strategy_summary"] = strategy_summary
    constraints_struct = (
        progress_state.get("render_constraints_struct") or default_constraints_struct()
    )

    executor_output = render_executor_output(
        state,
        deps=deps,
        conversation_mode=conversation_mode,
        policy_pack_active=policy_pack_active,
        policy_id=policy_id,
        persona_profile=persona_profile,
        scene_profile=scene_profile,
        style_contract=style_contract,
        constraints_struct=constraints_struct,
        strategy_summary=strategy_summary,
        memory_block=memory_block,
        world_state=state.get("world_state", {}),
        user_message=user_message,
    )

    state["executor_output"] = executor_output
    state["assistant_message"] = executor_output.get("response_text", "")
    state["response"] = state["assistant_message"]
    state["executor_render_meta"] = {
        "policy_id": policy_id,
        "conversation_mode": conversation_mode,
        "policy_pack_active": policy_pack_active,
        "persona_id": (persona_profile or {}).get("persona_id", "default"),
        "scene_id": (scene_profile or {}).get("scene_id", "default_chat"),
        "style_id": (style_contract or {}).get("style_id", "default"),
        "mode_confidence": progress_state.get("mode_confidence", 0.0),
        "constraints": {
            "disallow_numbers": constraints_struct.get("disallow_numbers", False),
            "max_questions": constraints_struct.get("max_questions"),
        },
    }

    repaired_response, violations, validator_meta = validate_and_repair(
        state["assistant_message"],
        constraints_struct,
        executed,
        state.get("world_state", {}),
        persona_profile=persona_profile,
        scene_profile=scene_profile,
        style_contract=style_contract,
    )
    if validator_meta.get("fallback_applied"):
        executor_output = dict(executor_output)
        executor_output["response_text"] = repaired_response
        executor_output = normalize_executor_output(executor_output)
        state["executor_output"] = executor_output
        state["assistant_message"] = executor_output.get("response_text", "")
        state["response"] = state["assistant_message"]

    if violations:
        logger.info("executor_response_validated=%s violations=%s", repaired_response, violations)

    state["executor_validator_meta"] = validator_meta
    override_policy_id = validator_meta.get("override_policy_id")
    state["override_policy_id"] = override_policy_id
    if override_policy_id:
        executed_override = dict(executed)
        executed_override["policy_id"] = override_policy_id
        state["executed_policy"] = executed_override
    state["override_reason"] = validator_meta.get("override_reason")
    return state
