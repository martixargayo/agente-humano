import json
import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

os.environ.setdefault("OPENAI_API_KEY", "dummy")

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from state import SessionState
import negotiation.negotiation_graph as negotiation_graph


def _fake_plan_policy(*_args, **_kwargs):
    decision = default_policy_decision()
    decision["policy_id"] = "info_extract_critical"
    decision["micro_goal"] = "Pedir información clave."
    return decision, {"planner_meta": {"mock": True}}


def _fake_update_belief_state(*_args, **_kwargs):
    return default_belief_state(), {"belief_meta": {"mock": True}}


def _fake_execute(_messages):
    return "ok"


def _slots_missing(intent_state):
    required = set(intent_state.get("slots", {}).get("slots_required", []))
    filled = set(intent_state.get("slots", {}).get("slots_filled", {}).keys())
    return sorted(required - filled)


def _print_turn(turn_label, state):
    trace = state.debug_trace[-1]
    intent_state = state.progress_state.get("intent_state", {})
    intent_meta = trace.get("planner_meta", {}).get("intent_meta", {})
    payload = {
        "turn": turn_label,
        "meta": {
            "intent_transition": intent_meta.get("intent_transition", ""),
            "decision": intent_meta.get("intent_decision", ""),
            "reasons": intent_meta.get("reasons", []),
            "retarget_slot": intent_meta.get("retarget_slot", ""),
            "replan_to": intent_meta.get("replan_to", ""),
            "pivot_reason": intent_meta.get("pivot_reason", ""),
            "pivot_strategy": intent_meta.get("pivot_strategy", ""),
        },
        "hint": {
            "step_kind": trace.get("intent_step_kind", ""),
            "target_slot": trace.get("intent_target_slot", ""),
            "slots_missing": _slots_missing(intent_state),
        },
        "intent": {
            "status": intent_state.get("status", ""),
            "intent_type": intent_state.get("intent_type", ""),
            "step_idx": intent_state.get("step_idx", 0),
            "step_attempts": intent_state.get("step_attempts", 0),
            "current_step": (intent_state.get("steps") or [{}])[intent_state.get("step_idx", 0)],
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _queue_world_states(world_states):
    queue = list(world_states)

    def fake_update_world_state(_prev_world, _user_message):
        if queue:
            return queue.pop(0)
        return default_world_state()

    negotiation_graph.update_world_state = fake_update_world_state
    negotiation_graph.get_negotiation_rag_index = lambda: None
    negotiation_graph.normalize_text = lambda raw_reply, last_user_message=None: raw_reply


def run_conversation(label, world_states, messages, seed_intent=None):
    _queue_world_states(world_states)
    deps = AgentDeps(
        plan_policy=_fake_plan_policy,
        update_belief_state=_fake_update_belief_state,
        execute=_fake_execute,
    )
    state = SessionState(user_id=f"user-{label}", session_id=f"session-{label}")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    state.progress_state = default_progress_state()
    if seed_intent is not None:
        state.progress_state["intent_state"] = deepcopy(seed_intent)

    for idx, message in enumerate(messages, start=1):
        run_negotiation_agent(state, message, deps=deps)
        _print_turn(f"{label}-{idx}", state)


if __name__ == "__main__":
    world_turn1 = default_world_state()
    world_turn2 = default_world_state()
    world_turn2.update({"batna_claimed": True, "batna_text": "Otra oferta"})
    world_turn3 = default_world_state()
    world_turn3.update(
        {
            "batna_claimed": True,
            "batna_text": "Otra oferta",
            "urgency_claimed": True,
            "urgency_text": "Necesito vender ya",
        }
    )

    run_conversation(
        "S1",
        [world_turn1, world_turn2, world_turn3],
        ["no sé", "tengo otra oferta", "me urge vender"],
    )

    seed_intent = default_intent_state()
    seed_intent.update(
        {
            "status": "active",
            "intent_goal": "Buscar BATNA",
            "intent_type": "info_extract",
            "steps": [
                {
                    "kind": "probe_open",
                    "target_slot": "seller_batna",
                    "success_if_filled": ["seller_batna"],
                }
            ],
            "step_idx": 0,
            "step_attempts": 0,
            "slots": {
                "slots_required": ["seller_batna", "seller_urgency_reason"],
                "slots_optional": [],
                "slots_filled": {},
            },
        }
    )

    world_turn = default_world_state()
    world_turn.update({"price_firm": True, "price_firm_text": "Precio firme"})

    run_conversation(
        "S2",
        [world_turn],
        ["precio firme"],
        seed_intent=seed_intent,
    )
