from __future__ import annotations

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


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    deps: AgentDeps = DEFAULT_DEPS,
    explicit_preset_id: str | None = None,
) -> Tuple[str, SessionState]:
    del explicit_preset_id
    add_message(state, "user", user_message)

    long_memory, short_memory, memory_meta = build_memory_context(
        state.history,
        state.summary,
        keep_last_n_turns=4,
    )

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

    if response:
        add_message(state, "assistant", response)

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
        }
    )
    return response, state
