from __future__ import annotations

from pathlib import Path

from evaluacion.contracts.models import TrajectoryRunnerInputV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.engine.flow_config import TRAJECTORY_MODEL
from evaluacion.engine.runners.common import load_prompt_text, run_structured

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "trajectory_evaluator_prompt.txt"


def _fallback_output(trajectory_input: TrajectoryRunnerInputV1) -> TurnTrajectoryV1:
    rows: list[TrajectoryTurn] = []
    prev = 45
    for turn in trajectory_input.turns_for_trajectory:
        score = min(prev + 3, 88)
        delta = score - prev
        direction = "up" if delta > 0 else "flat" if delta == 0 else "down"
        rows.append(
            TrajectoryTurn(
                turn_index=turn.turn_index,
                agreement_closeness_score_0_100=score,
                delta_vs_previous=delta,
                direction=direction,
                user_excerpt=turn.user_text[:140],
                counterpart_excerpt=turn.assistant_text[:140],
                impact_reason="Turno con avance moderado en entendimiento.",
                counterpart_thought_effect="Percibe posibilidad de progreso.",
                better_rephrase="Podemos concretar condiciones y cerrar si te encaja.",
            )
        )
        prev = score

    if not rows:
        rows = [
            TrajectoryTurn(
                turn_index=1,
                agreement_closeness_score_0_100=40,
                delta_vs_previous=0,
                direction="flat",
                user_excerpt="Sin turnos suficientes.",
                counterpart_excerpt="Sin turnos suficientes.",
                impact_reason="Evidencia insuficiente.",
                counterpart_thought_effect="Sin señal clara.",
                better_rephrase="Abrir con objetivo y contexto claros.",
            )
        ]

    largest_gain = max(rows, key=lambda r: r.delta_vs_previous).turn_index
    largest_drop = min(rows, key=lambda r: r.delta_vs_previous).turn_index
    return TurnTrajectoryV1(
        schema_version="turn_trajectory.v1",
        trajectory=rows,
        trend_label="upward_moderate",
        largest_drop_turn_index=largest_drop,
        largest_gain_turn_index=largest_gain,
    )


def run_trajectory_evaluator(trajectory_input: TrajectoryRunnerInputV1) -> tuple[TurnTrajectoryV1, str]:
    prompt = load_prompt_text(PROMPT_PATH)
    parsed = run_structured(
        model=TRAJECTORY_MODEL,
        developer_prompt=prompt,
        user_payload=trajectory_input.model_dump(mode="json"),
        output_model=TurnTrajectoryV1,
        schema_name="turn_trajectory_v1",
    )
    if parsed is None:
        return _fallback_output(trajectory_input), "fallback_no_api_key"
    return TurnTrajectoryV1.model_validate(parsed), "model"
