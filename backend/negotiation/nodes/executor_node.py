from __future__ import annotations

import json
import logging
import os
import time

from langchain_core.messages import HumanMessage, SystemMessage

from ..executor import normalize_executor_output, render_executor_output
from ..llm_clients import get_executor_finalizer_llm
from ..llm_planning_context import build_full_roleplay_profiles
from ..phase_map import get_phase_map_v1
from ..schemas import (
    default_constraints_struct,
    default_policy_decision,
    default_progress_state,
)
from ..state.deps import DEFAULT_DEPS, get_last_execute_meta
from ..telemetry.llm_usage import extract_llm_usage
from ..telemetry.trace_runtime import record_llm_call
from ..elementos.render.executor_prompts import (
    EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT,
    EXECUTOR_FINALIZER_V1_USER_PROMPT,
)

logger = logging.getLogger(__name__)


def _ensure_objective(state: dict) -> None:
    if not state.get("objective"):
        state["objective"] = ""


def _extract_marker(text: str, marker: str) -> str:
    for line in str(text or "").splitlines():
        if line.strip().lower().startswith(f"{marker.lower()}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _parse_objective_delta_and_tactic(next_move_hint: str) -> tuple[str, str]:
    objective_delta = _extract_marker(next_move_hint, "OBJECTIVE_DELTA").lower().strip()
    tactic = _extract_marker(next_move_hint, "TACTIC").lower().strip()
    if objective_delta not in {"reduce_risk", "improve_price", "gain_commitment", "test_consistency", "move_to_close"}:
        objective_delta = "reduce_risk"
    if tactic not in {"frame", "anchor", "conditional_offer", "tradeoff", "boundary", "silence"}:
        tactic = "frame"
    return objective_delta, tactic


def _safe_json_load(raw: str) -> dict:
    try:
        data = json.loads(str(raw or ""))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _finalizer_enabled() -> bool:
    return str(os.getenv("NEGOTIATION_EXECUTOR_FINALIZER_ENABLED", "0") or "1").strip().lower() in {"1", "true", "yes", "on"}


def _finalizer_mode() -> str:
    mode = str(os.getenv("NEGOTIATION_EXECUTOR_FINALIZER_MODE", "active") or "active").strip().lower()
    return mode if mode in {"active", "shadow"} else "active"


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
    executor_draft = dict(executor_output)

    planner_semantic_output = state.get("planner_semantic_output") if isinstance(state.get("planner_semantic_output"), dict) else {}
    next_move_hint = str(planner_semantic_output.get("next_move_hint") or "")
    objective_delta, tactic = _parse_objective_delta_and_tactic(next_move_hint)
    topic_selected = str(state.get("topic_selected") or "")
    phase_effective = str(planner_semantic_output.get("phase", "clima_humano") or "clima_humano")
    phase_prev = str((((progress_state or {}).get("phase_state") or {}).get("phase") or "clima_humano"))

    finalizer_called = False
    finalizer_changed_from_draft = False
    finalizer_fixes: list[str] = []
    latency_ms_finalizer = 0

    if _finalizer_enabled():
        finalizer_called = True
        finalizer_mode = _finalizer_mode()
        max_words = int((style_contract or {}).get("max_words") or 30)
        max_questions = int((style_contract or {}).get("max_questions") or 1)
        target_words = min(max_words, 26)
        prev_turn_asked_question = bool(progress_state.get("last_executor_asked_question", False))

        semantic_ledger = state.get("effective_semantic_ledger") if isinstance(state.get("effective_semantic_ledger"), dict) else ((progress_state or {}).get("semantic_ledger") if isinstance((progress_state or {}).get("semantic_ledger"), dict) else {})
        memory_short_compact = str(state.get("short_memory") or "") or "SIN_MEMORIA_CORTA_AUN"
        memory_long_compact = str(state.get("long_memory") or "") or "SIN_RESUMEN_AUN"

        finalizer_user_prompt = EXECUTOR_FINALIZER_V1_USER_PROMPT.format(
            target_words=target_words,
            max_words=max_words,
            max_questions=max_questions,
            prev_turn_asked_question=str(prev_turn_asked_question).lower(),
            last_seller_utterance=str(state.get("last_seller_utterance") or ""),
            user_message=str(user_message or ""),
            assistant_last_message=str(state.get("assistant_last_message") or state.get("last_assistant_message") or ""),
            phase=phase_effective,
            prev_phase=phase_prev,
            topic_selected=topic_selected,
            objective_delta=objective_delta,
            tactic=tactic,
            planner_semantic_output_json=json.dumps(planner_semantic_output, ensure_ascii=False),
            semantic_ledger_json=json.dumps(semantic_ledger or {}, ensure_ascii=False),
            memory_short_compact=memory_short_compact,
            memory_long_compact=memory_long_compact,
            executor_draft_json=json.dumps(executor_draft, ensure_ascii=False),
        )

        finalizer_started = time.perf_counter()
        llm = get_executor_finalizer_llm()
        raw = llm.invoke([
            SystemMessage(content=EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT),
            HumanMessage(content=finalizer_user_prompt),
        ])
        latency_ms_finalizer = int((time.perf_counter() - finalizer_started) * 1000)
        usage = extract_llm_usage(raw)
        parsed = _safe_json_load(getattr(raw, "content", str(raw)))
        final_candidate = normalize_executor_output(parsed)

        finalizer_changed_from_draft = bool(final_candidate != executor_draft)
        if str(final_candidate.get("response_text") or "") != str(executor_draft.get("response_text") or ""):
            finalizer_fixes.append("dialogue_fit")
        if bool(final_candidate.get("asked_question")) != bool(executor_draft.get("asked_question")):
            finalizer_fixes.append("question_policy")
        if len(str(final_candidate.get("response_text") or "").split()) < len(str(executor_draft.get("response_text") or "").split()):
            finalizer_fixes.append("brevity")

        record_llm_call(
            state,
            name="executor_finalizer_llm",
            node="executor_finalizer",
            started=finalizer_started,
            ok=True,
            model=usage.get("model"),
            tokens_in=usage.get("tokens_in"),
            tokens_out=usage.get("tokens_out"),
            retry_count=0,
            input_prompt_rendered=f"[system]\n{EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT}\n\n[user]\n{finalizer_user_prompt}",
            output_text_rendered=getattr(raw, "content", str(raw)),
            input_payload_raw={
                "objective_delta": objective_delta,
                "tactic": tactic,
                "mode": finalizer_mode,
            },
            output_payload_raw=final_candidate,
        )

        if finalizer_mode == "active":
            executor_output = final_candidate

    executor_output = normalize_executor_output(executor_output)

    render_meta = dict(executor_output.get("render_meta") or {}) if isinstance(executor_output.get("render_meta"), dict) else {}
    render_meta["finalizer_called"] = finalizer_called
    render_meta["finalizer_changed_from_draft"] = finalizer_changed_from_draft
    render_meta["finalizer_fixes"] = finalizer_fixes[:6]
    render_meta["latency_ms_finalizer"] = latency_ms_finalizer
    render_meta["objective_delta"] = objective_delta
    render_meta["tactic"] = tactic
    executor_output["render_meta"] = render_meta

    phase_candidate = state.get("phase_candidate") if isinstance(state.get("phase_candidate"), dict) else {}
    progress_state["phase_state"] = {
        "phase": phase_effective,
        "phase_effective": phase_effective,
        "confidence": float((phase_candidate or {}).get("confidence", 0.7) or 0.7),
        "reasons": list((phase_candidate or {}).get("reasons", []) or [])[:6],
        "last_updated_turn": int(state.get("turn_count", 0) or 0),
    }
    progress_state["last_executor_asked_question"] = bool(executor_output.get("asked_question", False))

    state["executor_output_draft"] = executor_draft
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
            "finalizer_called": finalizer_called,
            "finalizer_changed_from_draft": finalizer_changed_from_draft,
            "finalizer_fixes": finalizer_fixes,
            "latency_ms_finalizer": latency_ms_finalizer,
        },
    }
    return state
