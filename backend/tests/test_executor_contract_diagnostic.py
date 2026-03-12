from __future__ import annotations

from negociacion.guards.output import _planner_contract_signals
from negociacion.nodes.executor_node import ExecutorOutput
from negociacion.nodes.planner_node import PlannerContentPlan, PlannerLimits, PlannerOutput
from negociacion.orchestration.flow_config import _accept_or_fallback_executor_output, _evaluate_stub


def _planner_plan_counter() -> PlannerOutput:
    return PlannerOutput(
        schema_version="planner.v3",
        status="plan",
        turn_goal="Realizar una contraoferta pequeña y defendible",
        decision="counter",
        content_plan=PlannerContentPlan(
            must_include=["Contraoferta de 6500 €"],
            must_avoid=["Introducir condiciones adicionales", "Hacer preguntas"],
        ),
        limits=PlannerLimits(
            max_sentences=1,
            max_questions=0,
            allow_topic_shift=False,
            allow_personal_disclosure=False,
        ),
        memory_targets=[],
        done_criteria=["contraoferta_emitida"],
    )


def _planner_clarify() -> PlannerOutput:
    return PlannerOutput(
        schema_version="planner.v3",
        status="clarify",
        turn_goal="Pedir el dato mínimo para continuar",
        decision="ask",
        content_plan=PlannerContentPlan(
            must_include=["Pregunta una única aclaración"],
            must_avoid=["Dar propuesta definitiva"],
        ),
        limits=PlannerLimits(
            max_sentences=1,
            max_questions=1,
            allow_topic_shift=False,
            allow_personal_disclosure=False,
        ),
        memory_targets=[],
        done_criteria=["aclaracion_minima_emitida"],
    )


def _planner_refuse() -> PlannerOutput:
    return PlannerOutput(
        schema_version="planner.v3",
        status="refuse",
        turn_goal="Rechazar bajo reglas vigentes",
        decision="reject",
        content_plan=PlannerContentPlan(
            must_include=["No puedo continuar con esta solicitud"],
            must_avoid=["Dar detalles internos"],
        ),
        limits=PlannerLimits(
            max_sentences=1,
            max_questions=0,
            allow_topic_shift=False,
            allow_personal_disclosure=False,
        ),
        memory_targets=[],
        done_criteria=["negativa_emitida"],
    )


def _executor_meta_clarify() -> ExecutorOutput:
    return ExecutorOutput(
        schema_version="executor.v1",
        status="clarify",
        spoken_text=(
            "¿Quieres que mantenga la oferta de 6500€ como base y esperemos la respuesta de Joaqui, "
            "o prefieres ajustar algún tema antes de presentar la contraoferta?"
        ),
        memory_used=[],
        refusal_reason=None,
    )


def test_contract_signals_still_flag_plan_that_does_not_deliver() -> None:
    planner = _planner_plan_counter()
    executor = _executor_meta_clarify()

    signals = _planner_contract_signals(planner, executor)

    assert signals.planner_status == "plan"
    assert signals.executor_status == "clarify"
    assert "plan_should_deliver" in signals.violations


def test_eval_stub_no_longer_considers_plan_plus_clarify_as_aligned() -> None:
    planner = _planner_plan_counter()
    executor = _executor_meta_clarify()

    grades = _evaluate_stub(planner, executor)

    assert grades.planner_executor_agreement is False


def test_observe_only_keeps_output_even_if_plan_status_mismatches() -> None:
    planner = _planner_plan_counter()
    executor = _executor_meta_clarify()

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, executor)

    assert violation is not None
    assert accepted == executor
    assert enforced is False


def test_max_questions_is_not_hard_contract_in_observe_mode() -> None:
    planner = _planner_plan_counter()
    executor = ExecutorOutput(
        schema_version="executor.v1",
        status="deliver",
        spoken_text="Hola. ¿Cómo estás? Contraoferta de 6500 €.",
        memory_used=[],
        refusal_reason=None,
    )

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, executor)

    assert violation is None
    assert accepted == executor
    assert enforced is False


def test_observe_only_records_must_include_gap_without_replacing_output() -> None:
    planner = _planner_plan_counter()
    poor = ExecutorOutput(
        schema_version="executor.v1",
        status="deliver",
        spoken_text="Entiendo tu postura.",
        memory_used=[],
        refusal_reason=None,
    )

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, poor)

    assert violation == "plan_missing_must_include"
    assert accepted == poor
    assert enforced is False


def test_strict_mode_can_enforce_fallback_for_must_include_gap() -> None:
    planner = _planner_plan_counter()
    poor = ExecutorOutput(
        schema_version="executor.v1",
        status="deliver",
        spoken_text="Entiendo tu postura.",
        memory_used=[],
        refusal_reason=None,
    )

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, poor, "strict")

    assert violation == "plan_missing_must_include"
    assert accepted.status == "deliver"
    assert accepted.spoken_text == "Entiendo. Te respondo de forma clara y directa."
    assert enforced is True


def test_clarify_remains_legitimate_when_planner_status_is_clarify() -> None:
    planner = _planner_clarify()
    executor = ExecutorOutput(
        schema_version="executor.v1",
        status="clarify",
        spoken_text="¿Cuál sería tu cifra final para poder cerrar?",
        memory_used=[],
        refusal_reason=None,
    )

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, executor)

    assert violation is None
    assert accepted == executor
    assert enforced is False


def test_refuse_remains_legitimate_when_planner_status_is_refuse() -> None:
    planner = _planner_refuse()
    executor = ExecutorOutput(
        schema_version="executor.v1",
        status="refuse",
        spoken_text="No puedo ayudar con esa solicitud.",
        memory_used=[],
        refusal_reason="policy_refusal",
    )

    accepted, violation, enforced = _accept_or_fallback_executor_output(planner, executor)

    assert violation is None
    assert accepted == executor
    assert enforced is False
