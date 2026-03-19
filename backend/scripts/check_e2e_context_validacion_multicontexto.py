from __future__ import annotations

import json
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from evaluacion.contracts.models import FeedbackReportCoreV1, TrajectoryTurn, TurnTrajectoryV1
from evaluacion.storage import REPOSITORY
from negociacion.contexts import (
    NEGOTIATION_CONTEXT_WORLD_STATE_KEY,
    resolve_negotiation_context,
    resolve_public_context_selection,
)
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from sessions.state import SESSIONS, get_session_state

TARGET_CONTEXT_ID = "validacion_multicontexto"
TARGET_PUBLIC_SLUG = "negociacion-validacion"
BASELINE_CONTEXT_ID = "baseline_current"
BASELINE_PUBLIC_SLUG = "negociacion"


def _seed_history(state) -> None:
    state.history = [
        {"role": "user", "content": "Hola, vengo a ver el Mustang."},
        {"role": "assistant", "content": "Buenas, sí, sigue disponible."},
        {"role": "user", "content": "Me interesa, pero quiero entender mejor el estado real."},
        {"role": "assistant", "content": "Te cuento lo que se le ha hecho y lo que falta."},
        {"role": "user", "content": "Si el coche está fino podríamos hablar de números."},
        {"role": "assistant", "content": "Perfecto, dime por dónde quieres empezar."},
    ]


def _fake_runtime_turn(current_state, user_message: str, current_config):
    traces_key = f"{current_config.memory_key}_traces"
    traces = current_state.world_state.setdefault(traces_key, [])
    turn_index = len(traces) + 1
    canonical = current_state.world_state.setdefault(
        current_config.memory_key,
        {
            "openai_thread": {
                "thread_mode": current_config.thread_mode_default.value,
                "conversation_id": None,
                "previous_response_id": None,
            },
            "planner_state": {"current_phase": "descubrimiento_y_comprension"},
            "ui_state": {"finish_button_armed": False},
        },
    )
    thread = canonical.setdefault("openai_thread", {})
    if not thread.get("conversation_id"):
        thread["conversation_id"] = f"conv-{current_state.session_id}"
    thread["previous_response_id"] = f"resp-{turn_index}"
    if turn_index >= 3:
        canonical.setdefault("ui_state", {})["finish_button_armed"] = True
    trace = {
        "turn_id": f"{current_state.session_id}-turn-{turn_index}",
        "turn_started_at": f"2026-03-19T12:30:0{turn_index}+00:00",
        "timestamp_utc": f"2026-03-19T12:30:0{turn_index}+00:00",
        "conversation_id_before": thread["conversation_id"],
        "conversation_id_after": thread["conversation_id"],
        "previous_response_id_before": f"resp-{turn_index-1}" if turn_index > 1 else None,
        "previous_response_id_after": thread["previous_response_id"],
        "final_reply_text": f"[{TARGET_CONTEXT_ID}] turno {turn_index}: respuesta a {user_message}",
        "final_status": "ok",
        "guardrails_triggered": False,
        "logs": [],
        "nodes": {},
    }
    traces.append(trace)
    current_state.world_state[current_config.memory_key] = canonical
    return trace["final_reply_text"], current_state


def _core_output() -> FeedbackReportCoreV1:
    return FeedbackReportCoreV1.model_validate(
        {
            "schema_version": "feedback_report_core.v1",
            "score_global_100": 74,
            "interaction_outcome": "partial_progress",
            "summary_2_3_lines": "La conversación avanzó con continuidad y sin mezclar contextos.",
            "evaluation_blocks": [
                {"block_id": "valores", "title": "Valores", "status_visual": "correcto", "score_0_100": 74, "checks": [{"polarity": "check", "micro_explanation": "ok", "evidence_turn_indexes": [1]}], "block_verdict": "ok"},
                {"block_id": "vision", "title": "Visión", "status_visual": "correcto", "score_0_100": 74, "checks": [{"polarity": "check", "micro_explanation": "ok", "evidence_turn_indexes": [2]}], "block_verdict": "ok"},
                {"block_id": "relacion", "title": "Relación", "status_visual": "correcto", "score_0_100": 74, "checks": [{"polarity": "check", "micro_explanation": "ok", "evidence_turn_indexes": [3]}], "block_verdict": "ok"},
                {"block_id": "proceso", "title": "Proceso", "status_visual": "correcto", "score_0_100": 74, "checks": [{"polarity": "check", "micro_explanation": "ok", "evidence_turn_indexes": [3]}], "block_verdict": "ok"},
            ],
            "best_moment": {"turn_index": 2, "why": "Hubo foco y continuidad.", "impact": "Consolidó claridad útil."},
            "most_delicate_moment": {"turn_index": 3, "why": "Aparece presión negociadora.", "impact": "Exige cuidar límites."},
            "turning_point": {"turn_index": 3, "why": "Se abre el terreno de oferta.", "impact": "La conversación pasa a ajuste."},
            "recommendations": [{"title": "Seguir", "description": "Mantener reciprocidad.", "example": {"original_excerpt": "x", "better_rephrase": "y"}}],
        }
    )


def _trajectory_output() -> TurnTrajectoryV1:
    return TurnTrajectoryV1(
        schema_version="turn_trajectory.v1",
        trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=42, user_excerpt="u1", counterpart_excerpt="a1", impact_reason="base", counterpart_thought_effect="ok", better_rephrase="b1"),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=55, user_excerpt="u2", counterpart_excerpt="a2", impact_reason="progreso", counterpart_thought_effect="ok", better_rephrase="b2"),
            TrajectoryTurn(turn_index=3, agreement_closeness_score_0_100=63, user_excerpt="u3", counterpart_excerpt="a3", impact_reason="ajuste", counterpart_thought_effect="ok", better_rephrase="b3"),
        ],
    )


def _print_section(name: str, payload: Any) -> None:
    print(f"\n[{name}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()
    REPOSITORY._reports.clear()

    client = TestClient(app)
    resolved = resolve_negotiation_context(TARGET_CONTEXT_ID)
    baseline = resolve_negotiation_context(BASELINE_CONTEXT_ID)

    with ExitStack() as stack:
        stack.enter_context(patch("negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn", side_effect=_fake_runtime_turn))
        stack.enter_context(patch("evaluacion.engine.service.run_core_evaluator", return_value=(_core_output(), "gpt-5.4")))
        stack.enter_context(patch("evaluacion.engine.service.run_trajectory_evaluator", return_value=(_trajectory_output(), "gpt-5.4")))

        surface = {
            "public_page": client.get(f"/interfaz_usuario/{TARGET_PUBLIC_SLUG}").status_code,
            "bootstrap_endpoint": "/api/interfaz_usuario/sessions/bootstrap",
            "turn_endpoint": "/api/interfaz_usuario/negociacion/turn",
            "optimizer_bootstrap_endpoint": "/api/optimizador/sessions/bootstrap",
            "evaluation_endpoint": "/api/interfaz_usuario/feedback/evaluations",
            "selection": resolve_public_context_selection(public_slug=TARGET_PUBLIC_SLUG).model_dump(mode="json"),
            "frontend_reads_public_slug": True,
        }
        _print_section("surface", surface)

        boot = client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_ctx", "session_id": "s_ctx", "public_slug": TARGET_PUBLIC_SLUG},
        )
        assert boot.status_code == 200, boot.text
        state = get_session_state("u_ctx", "s_ctx")
        session_binding = {
            "bootstrap": boot.json(),
            "bound_context": state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
        }
        _print_section("session_binding", session_binding)

        turns = []
        for message in [
            "Hola, quiero entender bien el Mustang antes de hablar de precio.",
            "¿Qué mantenimiento importante tiene hecho?",
            "Si todo cuadra, podría moverme cerca de mercado pero necesito ver reciprocidad.",
        ]:
            response = client.post(
                "/api/interfaz_usuario/negociacion/turn",
                json={"user_id": "u_ctx", "session_id": "s_ctx", "message": message, "new_conversation": False},
            )
            assert response.status_code == 200, response.text
            turns.append(response.json())

        runtime_config = build_negotiation_pipeline_config(context_id=TARGET_CONTEXT_ID)
        runtime = {
            "prompts_dir": runtime_config.prompts_dir,
            "persona_path": str(resolved.persona_path),
            "negotiation_brief_path": str(resolved.negotiation_brief_path),
            "phase_cards_path": str(resolved.phase_cards_path),
            "phase_classifier_card_path": str(resolved.phase_classifier_card_path),
            "turns": turns,
            "latest_trace": state.world_state["negotiation_canonical_traces"][-1],
        }
        _print_section("runtime", runtime)

        new_conversation = client.post(
            "/api/interfaz_usuario/negociacion/new_conversation",
            json={"user_id": "u_ctx", "session_id": "s_ctx"},
        )
        assert new_conversation.status_code == 200, new_conversation.text
        new_session_id = new_conversation.json()["session_id"]
        new_state = get_session_state("u_ctx", new_session_id)
        rebound = {
            "new_conversation": new_conversation.json(),
            "new_bound_context": new_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
        }
        _print_section("new_conversation", rebound)

        conflict = client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_ctx", "session_id": "s_ctx", "context_id": BASELINE_CONTEXT_ID},
        )
        assert conflict.status_code == 409, conflict.text
        _print_section("conflict", conflict.json())

        _seed_history(state)
        eval_create = client.post(
            "/api/interfaz_usuario/feedback/evaluations",
            json={"user_id": "u_ctx", "session_id": "s_ctx"},
        )
        assert eval_create.status_code == 200, eval_create.text
        evaluation_id = eval_create.json()["evaluation_id"]
        eval_status = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}")
        eval_report = None
        for _ in range(20):
            eval_report = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report")
            if eval_report.status_code == 200:
                break
            time.sleep(0.05)
        assert eval_status.status_code == 200, eval_status.text
        assert eval_report is not None and eval_report.status_code == 200, eval_report.text if eval_report is not None else 'missing report'
        _print_section(
            "evaluation",
            {
                "create": eval_create.json(),
                "status": eval_status.json(),
                "provenance": eval_report.json()["report"]["provenance"],
                "summary": eval_report.json()["report"]["header"]["summary_2_3_lines"],
            },
        )

        opt_boot = client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_opt", "session_id": "s_opt", "context_id": TARGET_CONTEXT_ID},
        )
        assert opt_boot.status_code == 200, opt_boot.text
        opt_clone = client.post(
            "/api/optimizador/sandbox/clone",
            json={
                "optimizer_session_id": "opt-e2e",
                "source_user_id": "u_opt",
                "source_session_id": "s_opt",
                "source_conversation_id": "conv-opt",
            },
        )
        assert opt_clone.status_code == 200, opt_clone.text
        opt_new = client.post(
            "/api/optimizador/sandbox/new_conversation",
            json={"optimizer_session_id": "opt-e2e", "user_id": "u_opt", "session_id": "s_opt"},
        )
        assert opt_new.status_code == 200, opt_new.text
        sandbox_session_id = opt_new.json()["session_id"]
        sandbox_turn = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "opt-e2e",
                "user_id": "u_opt",
                "session_id": sandbox_session_id,
                "message": "Quiero validar el sandbox multi-context.",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        assert sandbox_turn.status_code == 200, sandbox_turn.text
        turn_id = sandbox_turn.json()["turn"]["turn_id"]
        traced_turn = client.get(f"/api/optimizador/turns/{turn_id}")
        traced_list = client.get(f"/api/optimizador/sessions/u_opt/{sandbox_session_id}/turns")
        assert traced_turn.status_code == 200, traced_turn.text
        assert traced_list.status_code == 200, traced_list.text
        optimizer = {
            "bootstrap": opt_boot.json(),
            "clone": opt_clone.json(),
            "new_conversation": opt_new.json(),
            "sandbox_turn": sandbox_turn.json(),
            "trace_turn": traced_turn.json().get("_optimizador"),
            "trace_reader": traced_list.json()["items"],
        }
        _print_section("optimizer", optimizer)

        coexist_baseline_boot = client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_base", "session_id": "s_base", "public_slug": BASELINE_PUBLIC_SLUG},
        )
        assert coexist_baseline_boot.status_code == 200, coexist_baseline_boot.text
        baseline_state = get_session_state("u_base", "s_base")
        coexistence = {
            "baseline_bootstrap": coexist_baseline_boot.json(),
            "baseline_context": baseline_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            "baseline_prompts_dir": str(build_negotiation_pipeline_config(context_id=BASELINE_CONTEXT_ID).prompts_dir),
            "alternate_context": state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            "alternate_prompts_dir": runtime_config.prompts_dir,
            "baseline_public_slug": baseline.public_slug,
            "alternate_public_slug": resolved.public_slug,
        }
        _print_section("coexistence", coexistence)

    print("\nresultado=ok")


if __name__ == "__main__":
    main()
