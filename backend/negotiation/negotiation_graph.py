from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Tuple

from state import SessionState, add_message

from .nodes.belief_node import belief_updater_node
from .nodes.executor_node import executor_node
from .nodes.planner_node import phase_policy_planner_node
from .nodes.progress_node import progress_updater_node
from .nodes.world_node import world_updater_node
from .schemas import (
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from .state.deps import AgentDeps, DEFAULT_DEPS
from .context_utils import build_memory_context
from .phase_map import get_phase_map_v1
from .state.deps import get_last_summarize_meta


_MEMORY_SHORT_TURNS = int(os.getenv("NEGOTIATION_MEMORY_SHORT_TURNS", "4") or 4)
_TURN_BUFFER_MARGIN = int(os.getenv("NEGOTIATION_TURN_BUFFER_MARGIN", "6") or 6)


@dataclass
class _SimpleApp:
    invoke_fn: Callable[[dict], dict]

    def invoke(self, state: dict) -> dict:
        return self.invoke_fn(state)


def _run_pipeline(state: dict) -> dict:
    state = world_updater_node(state)
    state = belief_updater_node(state)
    state = phase_policy_planner_node(state)
    state = progress_updater_node(state)
    state = executor_node(state)
    return state


negotiation_app = _SimpleApp(_run_pipeline)


def _last_assistant_message(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""


def _build_turn_blocks(messages: list[dict]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_user = ""
    current_assistant: list[str] = []
    for msg in messages:
        role = str(msg.get("role") or "").strip().lower()
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and not bool(msg.get("synthetic", False)):
            if current_user:
                blocks.append({"user": current_user, "assistant": "\n".join(current_assistant).strip()})
            current_user = content
            current_assistant = []
            continue
        if role == "assistant" and current_user:
            current_assistant.append(content)

    if current_user:
        blocks.append({"user": current_user, "assistant": "\n".join(current_assistant).strip()})
    return blocks


def _format_turn_blocks(blocks: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for block in blocks:
        user = str(block.get("user") or "").strip()
        assistant = str(block.get("assistant") or "").strip()
        if user:
            lines.append(f"user: {user}")
        if assistant:
            lines.append(f"assistant: {assistant}")
    return "\n".join(lines).strip()


def _build_short_memory_tail(messages: list[dict], *, short_turns: int) -> tuple[str, int, int | None]:
    blocks = _build_turn_blocks(messages)
    complete_blocks = [b for b in blocks if str(b.get("assistant") or "").strip()]
    if not complete_blocks:
        return "", 0, None
    short_turns = max(1, int(short_turns or 4))
    tail = complete_blocks[-short_turns:]
    text = _format_turn_blocks(tail)
    return text, len(tail), len(complete_blocks)


def _refresh_dual_memory(state: SessionState, deps: AgentDeps, *, short_turns: int) -> dict:
    progress_state = state.progress_state if isinstance(state.progress_state, dict) else default_progress_state()
    turn_buffer = _build_turn_blocks(state.history)
    total_turns = len(turn_buffer)
    short_turns = max(1, int(short_turns or 4))
    overflow_count = max(0, total_turns - short_turns)

    previous_summary = str(progress_state.get("memory_long") or state.summary or "").strip()
    summarized_turn_count = int(progress_state.get("memory_long_turns_summarized") or 0)
    summarized_turn_count = max(0, min(summarized_turn_count, overflow_count))

    memory_long_updated = False
    summarizer_called = False
    summary_tokens_in = None
    summary_tokens_out = None

    if overflow_count > summarized_turn_count:
        delta_blocks = turn_buffer[summarized_turn_count:overflow_count]
        new_block = _format_turn_blocks(delta_blocks)
        if new_block:
            summarize_fn = getattr(deps, "summarize", None)
            if callable(summarize_fn):
                summarizer_called = True
                previous_summary = str(summarize_fn(previous_summary, new_block) or "").strip()
                summarize_meta = get_last_summarize_meta()
                summary_tokens_in = summarize_meta.get("tokens_in")
                summary_tokens_out = summarize_meta.get("tokens_out")
            else:
                previous_summary = "\n\n".join([x for x in [previous_summary, new_block] if x]).strip()
            memory_long_updated = True
            summarized_turn_count = overflow_count

    start_idx = max(0, total_turns - short_turns)
    short_blocks = turn_buffer[start_idx:total_turns]
    short_text = _format_turn_blocks(short_blocks)
    long_text = str(previous_summary or "").strip()

    keep_turns = max(short_turns + max(1, _TURN_BUFFER_MARGIN), short_turns + 1)
    progress_state["turn_buffer"] = turn_buffer[-keep_turns:]
    progress_state["memory_short_turns"] = short_turns
    progress_state["memory_short"] = short_text
    progress_state["memory_long"] = long_text
    progress_state["memory_long_turns_summarized"] = summarized_turn_count
    state.progress_state = progress_state
    state.summary = long_text
    state.summary_meta = {
        "summarizer_called": summarizer_called,
        "summarizer_tokens_in": summary_tokens_in,
        "summarizer_tokens_out": summary_tokens_out,
        "memory_long_updated": memory_long_updated,
        "memory_long_turns_summarized": summarized_turn_count,
    }

    return {
        "memory_short_turns": short_turns,
        "memory_short_total_turns": len(short_blocks),
        "memory_long_total_turns_summarized": summarized_turn_count,
        "memory_long_updated": memory_long_updated,
        "summarizer_called": summarizer_called,
        "summarizer_tokens_in": summary_tokens_in,
        "summarizer_tokens_out": summary_tokens_out,
    }


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    deps: AgentDeps = DEFAULT_DEPS,
    explicit_preset_id: str | None = None,
) -> Tuple[str, SessionState]:
    del explicit_preset_id
    add_message(state, "user", user_message)

    progress_state_for_memory = state.progress_state if isinstance(state.progress_state, dict) else {}
    progress_keys_at_turn_start = sorted(str(k) for k in progress_state_for_memory.keys())
    has_persisted_short = "memory_short" in progress_state_for_memory or "turn_buffer" in progress_state_for_memory
    persisted_long = str(progress_state_for_memory.get("memory_long") or "").strip()

    if has_persisted_short:
        short_memory = str(progress_state_for_memory.get("memory_short") or "").strip()
        short_turns_rendered = sum(1 for line in short_memory.splitlines() if line.startswith("user:"))
        short_source = "progress_state"
        fallback_used = False
    else:
        short_memory, short_turns_rendered, _ = _build_short_memory_tail(state.history, short_turns=_MEMORY_SHORT_TURNS)
        short_source = "fallback_build_memory_context"
        fallback_used = True

    if persisted_long:
        long_memory = persisted_long
        long_source = "progress_state"
    else:
        long_memory, _legacy_short, _legacy_meta = build_memory_context(
            state.history,
            state.summary,
            keep_last_n_turns=_MEMORY_SHORT_TURNS,
        )
        long_source = "fallback_build_memory_context"

    memory_meta = {
        "chars_long": len(long_memory),
        "chars_short": len(short_memory),
        "turns_total": int(progress_state_for_memory.get("memory_long_turns_summarized") or 0) + int(progress_state_for_memory.get("memory_short_turns") or short_turns_rendered),
        "turns_short": int(progress_state_for_memory.get("memory_short_turns") or _MEMORY_SHORT_TURNS),
        "memory_short_source": short_source,
        "memory_long_source": long_source,
        "memory_short_turns_rendered": short_turns_rendered,
        "progress_state_keys_at_turn_start": progress_keys_at_turn_start,
        "memory_short_fallback_used": fallback_used,
    }

    graph_state = {
        "user_message": user_message,
        "objective": state.negotiation_objective or "",
        "constraints": "",
        "hard_constraints_struct": {},
        "world_state": state.world_state if isinstance(state.world_state, dict) and state.world_state else default_world_state(),
        "prev_world_state": state.world_state if isinstance(state.world_state, dict) and state.world_state else default_world_state(),
        "world_diff": {},
        "belief_state": state.belief_state if isinstance(state.belief_state, dict) and state.belief_state else default_belief_state(),
        "prev_belief_state": state.belief_state if isinstance(state.belief_state, dict) and state.belief_state else default_belief_state(),
        "belief_diff": {},
        "progress_state": state.progress_state if isinstance(state.progress_state, dict) and state.progress_state else default_progress_state(),
        "policy_decision": default_policy_decision(),
        "last_policy_executed": state.last_policy_executed,
        "phase_candidate": None,
        "phase_effective": None,
        "planner_meta": {},
        "planner_semantic_output": {},
        "semantic_judge": {},
        "advisor_recs": {},
        "recent_history_text": "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in state.history[-12:]),
        "last_assistant_message": _last_assistant_message(state.history),
        "assistant_last_message": _last_assistant_message(state.history),
        "short_memory": short_memory or "SIN_MEMORIA_CORTA_AUN",
        "long_memory": long_memory or "SIN_RESUMEN_AUN",
        "memory_meta": memory_meta,
        "phase_map_json": get_phase_map_v1(),
        "turn_count": state.turn_count,
        "deps": deps,
        "response": "",
    }

    new_graph_state = negotiation_app.invoke(graph_state)
    response = str(new_graph_state.get("response") or new_graph_state.get("assistant_message") or "")

    progress_state_out = new_graph_state.get("progress_state") or {}
    if not isinstance(progress_state_out, dict):
        progress_state_out = dict(progress_state_out)
    state.progress_state = progress_state_out

    if response:
        add_message(state, "assistant", response)

    refresh_meta = _refresh_dual_memory(state, deps, short_turns=_MEMORY_SHORT_TURNS)
    new_graph_state["progress_state"] = state.progress_state if isinstance(state.progress_state, dict) else {}
    new_graph_state["short_memory"] = str((state.progress_state or {}).get("memory_short") or "")
    new_graph_state["long_memory"] = str((state.progress_state or {}).get("memory_long") or "")
    new_graph_state["summary"] = new_graph_state["long_memory"]

    state.world_state = new_graph_state.get("world_state") if isinstance(new_graph_state.get("world_state"), dict) else state.world_state
    state.belief_state = new_graph_state.get("belief_state") if isinstance(new_graph_state.get("belief_state"), dict) else state.belief_state
    state.progress_state = new_graph_state.get("progress_state") if isinstance(new_graph_state.get("progress_state"), dict) else state.progress_state
    state.last_policy_executed = new_graph_state.get("policy_decision") if isinstance(new_graph_state.get("policy_decision"), dict) else state.last_policy_executed

    state.debug_trace.append(
        {
            "user_message": user_message,
            "assistant_message": response,
            "semantic_judge": new_graph_state.get("semantic_judge", {}),
            "planner_semantic_output": new_graph_state.get("planner_semantic_output", {}),
            "executor_output": new_graph_state.get("executor_output", {}),
            "progress_state": new_graph_state.get("progress_state", {}),
            "planner_meta": new_graph_state.get("planner_meta", {}),
            "world_judge_meta": ((new_graph_state.get("world_debug") or {}).get("world_judge_meta", {}) if isinstance(new_graph_state.get("world_debug"), dict) else {}),
            "trace_runtime": new_graph_state.get("trace_runtime", {}),
            "planner_ledger_hash": new_graph_state.get("planner_ledger_hash", ""),
            "executor_ledger_hash": new_graph_state.get("executor_ledger_hash", ""),
            "effective_ledger_hash": new_graph_state.get("effective_ledger_hash", ""),
            "ledger_mismatch_detected": ((new_graph_state.get("ledger_observability") or {}).get("ledger_mismatch_detected", False) if isinstance(new_graph_state.get("ledger_observability"), dict) else False),
            "turn_idx": int(state.turn_count or 0),
            "refresh_meta": refresh_meta,
        }
    )
    return response, state
