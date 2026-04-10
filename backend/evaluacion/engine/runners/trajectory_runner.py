from __future__ import annotations

from evaluacion.contracts.models import TrajectoryRunnerInputV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.domains.router import resolve_evaluation_assets
from evaluacion.engine.flow_config import TRAJECTORY_MODEL
from evaluacion.engine.runners.common import load_prompt_text, run_structured


def _fallback_output(trajectory_input: TrajectoryRunnerInputV1) -> TurnTrajectoryV1:
    rows: list[TrajectoryTurn] = []
    prev = 45
    for turn in trajectory_input.turns_for_trajectory:
        score = min(prev + 3, 88)
        rows.append(
            TrajectoryTurn(
                turn_index=turn.turn_index,
                agreement_closeness_score_0_100=score,
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
                user_excerpt="Sin turnos suficientes.",
                counterpart_excerpt="Sin turnos suficientes.",
                impact_reason="Evidencia insuficiente.",
                counterpart_thought_effect="Sin señal clara.",
                better_rephrase="Abrir con objetivo y contexto claros.",
            )
        ]

    conviction = rows[-1].agreement_closeness_score_0_100 if rows else 40
    return TurnTrajectoryV1(schema_version="turn_trajectory.v1", trajectory=rows, conviction_level_0_100=conviction)


def run_trajectory_evaluator(trajectory_input: TrajectoryRunnerInputV1) -> tuple[TurnTrajectoryV1, str]:
    prompt = load_prompt_text(resolve_evaluation_assets(trajectory_input.domain_context).trajectory_prompt_path)
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
