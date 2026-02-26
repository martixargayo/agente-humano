"""Replay suite mínima observacional para comportamiento conversacional.

Mide métricas sin validadores rígidos y sin asserts por keywords.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from negotiation.negotiation_graph import run_negotiation_agent
from state import get_session_state


@dataclass
class ReplayCase:
    name: str
    turns: list[str]


class _Raw:
    def __init__(self, content: str):
        self.content = content


class _PlannerStructuredDummy:
    def invoke(self, _messages):
        from negotiation.elementos.strategy_definitions import PlannerSemanticV1DecisionModel

        return PlannerSemanticV1DecisionModel(
            schema_version="planner_semantic_v1",
            phase="descubrimiento_y_comprension",
            style="Natural, alterna validación y avance.",
            next_move_hint="Responder con coherencia humana y avanzar sin repetir.",
            what_not_to_repeat=[],
        )


class _PlannerLlmDummy:
    model = "dummy-semantic-planner"
    model_name = "dummy-semantic-planner"

    def with_structured_output(self, _schema):
        return _PlannerStructuredDummy()

    def invoke(self, _messages):
        return _Raw(
            json.dumps(
                {
                    "schema_version": "judge_semantic_v1",
                    "topic_alignment": "on_topic",
                    "reason_short": "ok",
                    "semantic_ledger": {
                        "lo_que_ya_se_toco": ["estado general", "mantenimiento"],
                        "lo_que_ya_pregunte": ["precio esperado"],
                        "lo_que_falta_pero_no_insistire": [],
                    },
                    "ledger_update_notes": "ok",
                },
                ensure_ascii=False,
            )
        )


class _ExecutorLlmDummy:
    model = "dummy-semantic-executor"
    model_name = "dummy-semantic-executor"

    def invoke(self, messages):
        prompt = "\n".join(str(getattr(m, "content", "")) for m in messages)
        lower = prompt.lower()
        if "prefiero que lo digas tú" in lower:
            text = "Te entiendo. Para avanzar, te propongo un rango prudente y lo ajustamos si te encaja."
        elif "por qué" in lower and "estás dispuesto" in lower:
            text = "Me interesa por el modelo y su estado. Si te encaja, te propongo una referencia razonable para ambos."
        elif "mantenimiento" in lower:
            text = "Perfecto, mantenimiento entendido. Avancemos al siguiente punto cuando quieras."
        else:
            text = "Entendido, me encaja. Podemos avanzar hacia una propuesta de cierre cuando te vaya bien."

        return _Raw(
            json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": text,
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )
        )


def _patch_llms() -> None:
    import negotiation.nodes.world_node as world_node
    import negotiation.phase_policy_planner as planner_mod
    import negotiation.state.deps as deps_mod

    world_node.get_planner_llm = lambda: _PlannerLlmDummy()
    planner_mod.get_planner_llm = lambda: _PlannerLlmDummy()
    deps_mod.get_executor_llm = lambda: _ExecutorLlmDummy()


def _run_case(case: ReplayCase) -> dict:
    state = get_session_state("replay_user", case.name)
    state.history = []
    state.debug_trace = []
    state.turn_count = 0

    question_turns = 0
    total_turns = 0
    consecutive_q = 0
    max_consecutive_q = 0
    ledger_mismatch = 0

    for turn in case.turns:
        _, state = run_negotiation_agent(state, turn)
        trace = state.debug_trace[-1]
        total_turns += 1
        out = trace.get("executor_output") if isinstance(trace.get("executor_output"), dict) else {}
        asked = bool(out.get("asked_question", False))
        if asked:
            question_turns += 1
            consecutive_q += 1
            max_consecutive_q = max(max_consecutive_q, consecutive_q)
        else:
            consecutive_q = 0
        if bool(trace.get("ledger_mismatch_detected", False)):
            ledger_mismatch += 1

    return {
        "case": case.name,
        "turns": total_turns,
        "question_turn_rate": round(question_turns / max(1, total_turns), 3),
        "consecutive_question_streak": max_consecutive_q,
        "ledger_mismatch_rate": round(ledger_mismatch / max(1, total_turns), 3),
    }


def main() -> None:
    _patch_llms()
    cases = [
        ReplayCase(
            name="turnos_2_18_base",
            turns=[
                "Hola, ¿qué tal?",
                "Está bien cuidado el coche.",
                "Ya te conté el mantenimiento.",
                "¿Por qué te interesa y qué estás dispuesto a ofrecer?",
                "Prefiero que lo digas tú.",
                "Estoy dispuesto a venderlo por 8.500.",
            ],
        ),
        ReplayCase(name="direct_question_variant", turns=["¿Por qué te interesa?", "¿Qué ofreces tú?"]),
        ReplayCase(name="price_pushback_variant", turns=["Prefiero que lo digas tú.", "No, dime tú el rango."]),
        ReplayCase(
            name="paraphrase_repeat_variant",
            turns=["El mantenimiento está al día.", "Como te dije, lo he revisado cada año.", "Ya quedó claro el mantenimiento."],
        ),
    ]

    print("=== Replay behavior suite (observacional) ===")
    for case in cases:
        metrics = _run_case(case)
        print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
