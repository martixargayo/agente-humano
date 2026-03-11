from __future__ import annotations

from dataclasses import dataclass

from ..state.canonical_state import CanonicalState
from ..state.shared_types import NegotiationPhase


@dataclass(frozen=True)
class FinishButtonTriggerEvaluation:
    should_arm: bool
    reasons: tuple[str, ...] = ()


def evaluate_finish_button_triggers(canonical_state: CanonicalState) -> FinishButtonTriggerEvaluation:
    reasons: list[str] = []

    if canonical_state.planner_state.current_phase == NegotiationPhase.formalizacion_del_acuerdo:
        reasons.append("phase_formalizacion_del_acuerdo")

    if canonical_state.planner_state.current_phase == NegotiationPhase.abandono_de_la_negociacion:
        reasons.append("phase_abandono_de_la_negociacion")

    return FinishButtonTriggerEvaluation(should_arm=bool(reasons), reasons=tuple(reasons))
