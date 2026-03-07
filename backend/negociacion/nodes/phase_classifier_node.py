from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict

from .memory_node import DialogueMessage, TraceMeta, UserTurn
from ..state.shared_types import NegotiationPhase


class PhaseClassifierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous_phase: NegotiationPhase | None
    recent_phase_history: List[NegotiationPhase]
    recent_turns: List[DialogueMessage]
    current_user_turn: UserTurn
    trace_meta: TraceMeta


class PhaseClassifierOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: NegotiationPhase


def build_phase_classifier_input(
    *,
    previous_phase: NegotiationPhase | None,
    recent_phase_history: List[NegotiationPhase],
    recent_turns: List[DialogueMessage],
    current_user_turn: UserTurn,
    trace_meta: TraceMeta,
) -> PhaseClassifierInput:
    return PhaseClassifierInput(
        previous_phase=previous_phase,
        recent_phase_history=recent_phase_history,
        recent_turns=recent_turns,
        current_user_turn=current_user_turn,
        trace_meta=trace_meta,
    )


def build_phase_classifier_messages(phase_classifier_prompt: str, payload: PhaseClassifierInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": phase_classifier_prompt}, {"role": "user", "content": payload.model_dump_json()}]
