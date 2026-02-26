from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from negotiation.negotiation_graph import run_negotiation_agent
from state import get_session_state, SessionState


class _Raw:
    def __init__(self, content: str):
        self.content = content


class _PlannerStructuredDummy:
    def invoke(self, _messages):
        from negotiation.elementos.strategy_definitions import PlannerSemanticV1DecisionModel

        return PlannerSemanticV1DecisionModel(
            schema_version="planner_semantic_v1",
            phase="descubrimiento_y_comprension",
            style="Natural, humano y con progreso.",
            next_move_hint="Responder primero y avanzar sin repetir.",
            what_not_to_repeat=["No repetir mantenimiento ya cubierto."],
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
                        "lo_que_ya_se_toco": ["estado general", "mantenimiento", "motivo de venta"],
                        "lo_que_ya_pregunte": ["mantenimiento", "precio"],
                        "lo_que_falta_pero_no_insistire": ["kilometraje exacto"],
                    },
                    "ledger_update_notes": "actualizado",
                },
                ensure_ascii=False,
            )
        )


class _ExecutorLlmDummy:
    model = "dummy-semantic-executor"
    model_name = "dummy-semantic-executor"

    def invoke(self, _messages):
        return _Raw(
            json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Me interesa por el modelo y su estado. Si te encaja, te propongo un rango razonable para avanzar.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )
        )


def _patch_runtime_llms() -> None:
    import negotiation.nodes.world_node as world_node
    import negotiation.phase_policy_planner as planner_mod
    import negotiation.state.deps as deps_mod

    world_node.get_planner_llm = lambda: _PlannerLlmDummy()
    planner_mod.get_planner_llm = lambda: _PlannerLlmDummy()
    deps_mod.get_executor_llm = lambda: _ExecutorLlmDummy()


def _capture_runtime_prompts() -> dict:
    _patch_runtime_llms()
    state = get_session_state("literal_user", "literal_session")
    state.history = []
    state.debug_trace = []
    state.turn_count = 0

    run_negotiation_agent(state, "¿Por qué te interesa este coche y qué estarías dispuesto a ofrecer?")
    trace = state.debug_trace[-1]
    runtime_calls = (trace.get("trace_runtime") or {}).get("llm_calls", [])

    out: dict = {
        "planner": {},
        "executor": {},
        "world_judge": {},
        "trace": {
            "planner_ledger_hash": trace.get("planner_ledger_hash", ""),
            "executor_ledger_hash": trace.get("executor_ledger_hash", ""),
            "effective_ledger_hash": trace.get("effective_ledger_hash", ""),
            "ledger_mismatch_detected": trace.get("ledger_mismatch_detected", False),
        },
    }

    for call in runtime_calls:
        if call.get("name") == "planner_llm":
            out["planner"] = {
                "input_prompt_rendered": call.get("input_prompt_rendered", ""),
                "input_payload_raw": call.get("input_payload_raw"),
            }
        if call.get("name") == "executor_llm":
            out["executor"] = {
                "input_prompt_rendered": call.get("input_prompt_rendered", ""),
                "input_payload_raw": call.get("input_payload_raw"),
            }

    world_meta = trace.get("world_judge_meta") if isinstance(trace.get("world_judge_meta"), dict) else {}
    out["world_judge"] = {
        "judge_input_prompt_rendered": world_meta.get("judge_input_prompt_rendered", ""),
        "judge_output_text_rendered": world_meta.get("judge_output_text_rendered", ""),
    }

    return out


class _SummaryDummy:
    def __init__(self):
        self.captured_messages = None

    def invoke(self, messages):
        self.captured_messages = messages
        return type("R", (), {"content": "resumen actualizado"})()


def _capture_summary_prompt() -> dict:
    import agent

    dummy = _SummaryDummy()
    agent.summary_llm = dummy

    st = SessionState(user_id="sum_u", session_id="sum_s")
    # construir historial para forzar trim+summary por camino real
    st.history = []
    for i in range(14):
        st.history.append({"role": "user", "content": f"u{i}"})
        st.history.append({"role": "assistant", "content": f"a{i}"})

    agent._maybe_trim_and_summarize(st)

    msgs = dummy.captured_messages or []
    rendered = []
    for m in msgs:
        rendered.append({"role": getattr(m, "type", "unknown"), "content": str(getattr(m, "content", ""))})

    return {
        "messages": rendered,
        "summary_after": st.summary,
    }


def main() -> None:
    data = {
        "runtime": _capture_runtime_prompts(),
        "summary": _capture_summary_prompt(),
    }
    out_dir = ROOT / "docs" / "diagnostics" / "live_trace_findings" / "verification_prompts_literal"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt_capture.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(str(out_dir / "prompt_capture.json"))


if __name__ == "__main__":
    main()
