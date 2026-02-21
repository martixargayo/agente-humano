from __future__ import annotations

import logging
import re
import time

from ..context_utils import format_memory_block
from ..elementos.render import resolve_render_profiles
from ..elementos.render.carlos_buyer_preset import (
    get_carlos_constraints_struct,
    is_carlos_buyer_render_ids,
)
from ..executor import build_strategy_summary, normalize_executor_output, render_executor_output
from ..schemas import (
    default_constraints_struct,
    default_policy_decision,
    default_progress_state,
    default_render_state,
)
from ..state.deps import DEFAULT_DEPS, get_last_execute_meta
from ..validator import validate_and_repair
from ..telemetry.trace_runtime import record_llm_call

logger = logging.getLogger(__name__)


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def _enforce_executor_instruction(response_text: str, executor_instruction: dict) -> tuple[str, list[str]]:
    if not isinstance(executor_instruction, dict):
        return response_text, []
    repaired = response_text
    reasons: list[str] = []

    must_avoid = [str(x).lower() for x in executor_instruction.get("must_avoid", []) if str(x).strip()]
    lowered = repaired.lower()
    for token in must_avoid:
        if token and token in lowered:
            repaired = "Prefiero mantener una conversación constructiva para seguir avanzando."
            reasons.append(f"must_avoid:{token}")
            lowered = repaired.lower()

    max_q = executor_instruction.get("max_questions_per_turn", 2)
    try:
        max_q_int = max(0, int(max_q))
    except Exception:
        max_q_int = 2
    q_count = repaired.count("?")
    if q_count > max_q_int:
        parts = repaired.split("?")
        repaired = "?".join(parts[: max_q_int + 1]).strip()
        if not repaired.endswith("?") and max_q_int > 0:
            repaired = repaired.rstrip(" .") + "?"
        reasons.append("max_questions")

    safe_mode = str(executor_instruction.get("safe_mode", "normal") or "normal")
    if safe_mode == "deescalate":
        if any(token in lowered for token in ["idiota", "amenaza", "matar"]):
            repaired = "Entiendo la tensión; propongo bajar el tono y centrarnos en hechos verificables."
            reasons.append("safe_mode_deescalate")

    return repaired, reasons


def _enforce_constraints_struct(response_text: str, constraints_struct: dict) -> tuple[str, list[str]]:
    repaired = response_text
    reasons: list[str] = []
    if not isinstance(constraints_struct, dict):
        return repaired, reasons

    max_q = constraints_struct.get("max_questions")
    if isinstance(max_q, int) and max_q >= 0:
        q_count = repaired.count("?")
        if q_count > max_q:
            parts = repaired.split("?")
            repaired = "?".join(parts[: max_q + 1]).strip()
            if max_q > 0 and not repaired.endswith("?"):
                repaired = repaired.rstrip(" .") + "?"
            reasons.append("constraints:max_questions")

    if bool(constraints_struct.get("disallow_numbers", False)):
        if re.search(r"\d", repaired):
            repaired = re.sub(r"\d+[\d.,€$%]*", "", repaired)
            repaired = re.sub(r"\s{2,}", " ", repaired).strip()
            if not repaired:
                repaired = "Prefiero no dar cifras exactas en este punto; ¿te parece si revisamos condiciones?"
            reasons.append("constraints:disallow_numbers")

    return repaired, reasons


def _instruction_followed(response_text: str, executor_instruction: dict) -> tuple[bool, str]:
    if not isinstance(executor_instruction, dict):
        return True, ""

    instruction = str(executor_instruction.get("instruction", "") or "").strip()
    if not instruction:
        return True, ""

    asks = executor_instruction.get("ask", [])
    ask_tokens = [str(x).strip().lower() for x in asks if str(x).strip()]
    text_lower = response_text.lower()
    missing_ask = bool(ask_tokens) and not any(token in text_lower for token in ask_tokens)

    expects_question = any(
        marker in instruction.lower()
        for marker in ["pregunta", "preguntar", "indagar", "consultar", "ask"]
    )
    missing_question = expects_question and "?" not in response_text

    if missing_question:
        return False, "missing_question_for_instruction"
    if missing_ask:
        return False, "missing_required_ask_slot"
    return True, ""


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
    constraints_struct = progress_state.get("render_constraints_struct")
    if not isinstance(constraints_struct, dict):
        if is_carlos_buyer_render_ids(
            render_state.get("persona_id"),
            render_state.get("scene_id"),
            render_state.get("style_id"),
        ):
            constraints_struct = get_carlos_constraints_struct()
        else:
            constraints_struct = default_constraints_struct()

    llm_started = time.perf_counter()
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
        input_prompt_rendered=str(execute_meta.get("input_prompt_rendered", "")),
        output_text_rendered=str(execute_meta.get("output_text_rendered", "")),
        input_payload_raw=execute_meta.get("rendered_messages"),
        output_payload_raw=executor_output,
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

    instruction_repaired, instruction_reasons = _enforce_executor_instruction(
        repaired_response, state.get("executor_instruction", {})
    )
    if instruction_reasons and instruction_repaired != repaired_response:
        repaired_response = instruction_repaired
        violations = list(violations) + instruction_reasons
        validator_meta = dict(validator_meta)
        validator_meta["instruction_enforcement"] = instruction_reasons
        validator_meta["fallback_applied"] = True

    constraints_repaired, constraints_reasons = _enforce_constraints_struct(
        repaired_response, constraints_struct
    )
    if constraints_reasons and constraints_repaired != repaired_response:
        repaired_response = constraints_repaired
        violations = list(violations) + constraints_reasons
        validator_meta = dict(validator_meta)
        validator_meta["constraints_enforcement"] = constraints_reasons
        validator_meta["fallback_applied"] = True

    followed_instruction, deviation_reason = _instruction_followed(
        repaired_response, state.get("executor_instruction", {})
    )
    if not followed_instruction and "?" not in repaired_response:
        repaired_response = repaired_response.rstrip(" .") + "?"
        validator_meta = dict(validator_meta)
        validator_meta["fallback_applied"] = True
        followed_instruction, deviation_reason = _instruction_followed(
            repaired_response, state.get("executor_instruction", {})
        )
        if followed_instruction:
            validator_meta["instruction_enforcement"] = list(validator_meta.get("instruction_enforcement", [])) + [
                "instruction_autorepair_question",
            ]

    if validator_meta.get("fallback_applied"):
        executor_output = dict(executor_output)
        executor_output["response_text"] = repaired_response
        executor_output = normalize_executor_output(executor_output)
        state["executor_output"] = executor_output
        state["assistant_message"] = executor_output.get("response_text", "")
        state["response"] = state["assistant_message"]

    if violations:
        logger.info("executor_response_validated=%s violations=%s", repaired_response, violations)

    validator_meta = dict(validator_meta)
    validator_meta["executor_instruction_compliance"] = "pass" if not instruction_reasons else "repaired"
    validator_meta["executor_followed_instruction"] = followed_instruction
    validator_meta["deviation_reason"] = deviation_reason
    state["executor_validator_meta"] = validator_meta

    state["executor_debug_v2"] = {
        "policy_context": {
            "executed_policy_id": policy_id,
            "micro_goal": str((state.get("policy_decision") or {}).get("micro_goal", ""))[:180],
            "constraints_struct": constraints_struct,
            "safety_checks_applied": list((state.get("executor_instruction") or {}).get("must_avoid", []))[:6],
        },
        "render_pipeline": {
            "prompt_template_id": "EXECUTOR_USER_PROMPT_v1",
            "validators_run": [
                {"name": "validate_and_repair", "ok": not bool(violations), "issues_count": len(violations)},
                {"name": "executor_instruction_enforcement", "ok": not bool(instruction_reasons), "issues_count": len(instruction_reasons)},
            ],
            "post_repair": {
                "applied": bool(validator_meta.get("fallback_applied")),
                "reason": ",".join(instruction_reasons)[:140],
            },
        },
        "output_meta": {
            "response_length": len(state.get("assistant_message", "")),
            "constraints_respected": not bool(violations),
            "sanitizer_flags": list(validator_meta.get("validation_flags", []))[:8],
            "executor_followed_instruction": bool(followed_instruction),
            "deviation_reason": deviation_reason,
        },
    }
    override_policy_id = validator_meta.get("override_policy_id")
    state["override_policy_id"] = override_policy_id
    if override_policy_id:
        executed_override = dict(executed)
        executed_override["policy_id"] = override_policy_id
        state["executed_policy"] = executed_override
    state["override_reason"] = validator_meta.get("override_reason")
    return state
