from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .memory_node import DialogueMessage, TraceMeta, UserTurn
from ..state.shared_types import NegotiationPhase


class PhaseClassifierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["phase_classifier_input.v1"]
    previous_phase: NegotiationPhase | None
    recent_phase_history: List[NegotiationPhase]
    recent_turns: List[DialogueMessage]
    current_user_turn: UserTurn
    trace_meta: TraceMeta


class PhaseClassifierOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["phase_classifier.v1"]
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
        schema_version="phase_classifier_input.v1",
        previous_phase=previous_phase,
        recent_phase_history=recent_phase_history,
        recent_turns=recent_turns,
        current_user_turn=current_user_turn,
        trace_meta=trace_meta,
    )


def build_phase_classifier_messages(phase_classifier_prompt: str, payload: PhaseClassifierInput) -> List[dict[str, str]]:
    return [
        {"role": "developer", "content": phase_classifier_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `PhaseClassifierOutput`.\n\n<phase_classifier_input_json>\n"
            f"{payload.model_dump_json()}\n"
            "</phase_classifier_input_json>\n</task_input>",
        },
    ]
