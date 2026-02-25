from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict

WorldState = Dict[str, Any]
BeliefState = Dict[str, Any]
PolicyState = Dict[str, Any]
NegotiationPhase = Literal[
    "clima_humano",
    "descubrimiento_y_comprension",
    "propuesta_creativa",
    "concesiones_y_ajuste_final",
    "formalizacion_del_acuerdo",
]


class PolicyDecision(TypedDict):
    policy_id: str
    reason: str
    micro_goal: str
    risk_posture: str
    why_short: str
    inputs_used: List[str]


class ProgressState(TypedDict, total=False):
    semantic_ledger: Dict[str, List[str]]
    phase_state: Dict[str, Any]
    policy_state: Dict[str, Any]
    render_state: Dict[str, Any]
    render_constraints_struct: Dict[str, Any]
    conversation_mode: str


def default_world_state() -> WorldState:
    return {
        "interaction": {},
        "notes": {},
    }


def default_belief_state() -> BeliefState:
    return {
        "signals": {},
        "flags": {},
    }


def default_policy_decision() -> PolicyDecision:
    return {
        "policy_id": "semantic_ledger",
        "reason": "",
        "micro_goal": "",
        "risk_posture": "low",
        "why_short": "",
        "inputs_used": [],
    }


def default_policy_state() -> PolicyState:
    return {
        "policy_id": "semantic_ledger",
        "planner_request": "replan",
        "last_turn": 0,
        "started_turn": 0,
    }


def default_semantic_ledger() -> Dict[str, List[str]]:
    return {
        "lo_que_ya_se_toco": [],
        "lo_que_ya_pregunte": [],
        "lo_que_falta_pero_no_insistire": [],
    }


def default_render_state() -> Dict[str, Any]:
    return {
        "persona_id": "default",
        "scene_id": "default",
        "style_id": "default",
    }


def default_constraints_struct() -> Dict[str, Any]:
    return {
        "max_words": 30,
        "max_questions": 1,
    }


def default_progress_state() -> ProgressState:
    return {
        "semantic_ledger": default_semantic_ledger(),
        "phase_state": {
            "phase": "clima_humano",
            "phase_effective": "clima_humano",
            "confidence": 0.7,
            "reasons": [],
        },
        "policy_state": default_policy_state(),
        "render_state": default_render_state(),
        "render_constraints_struct": default_constraints_struct(),
        "conversation_mode": "general",
    }
