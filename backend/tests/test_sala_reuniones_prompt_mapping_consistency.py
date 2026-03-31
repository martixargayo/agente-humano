from __future__ import annotations

import re
import unittest

from negociacion.contexts import resolve_negotiation_context
from negociacion.contexts.prompt_io_mapping import load_prompt_io_adapter
from negociacion.nodes.memory_node import DialogueMessage, TraceMeta, UserTurn
from negociacion.nodes.planner_node import PlannerContentPlan, PlannerLimits, PlannerOutput
from negociacion.orchestration.flow_config import (
    build_executor_input,
    build_memory_input,
    build_phase_input,
    build_planner_input,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import ThreadMode


class SalaReunionesPromptMappingConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = resolve_negotiation_context("sala_reuniones")
        self.adapter = load_prompt_io_adapter(self.context.prompt_io_mapping_path)
        self.trace = TraceMeta(turn_id="t_diag", prompt_version="diag", schema_version="diag", model_target="diag-model")
        self.user_turn = UserTurn(
            raw_text="Podemos mover una hora.",
            normalized_text="podemos mover una hora",
            modality="text",
            language="es",
            timestamp_iso="2026-01-01T10:00:00+00:00",
        )
        self.recent = [
            DialogueMessage(role="assistant", text="Veo el conflicto de sala."),
            DialogueMessage(role="user", text="Necesitamos mañana temprano."),
        ]
        self.canonical = build_default_canonical_state(
            session_id="s_diag",
            user_id="u_diag",
            thread_mode=ThreadMode.conversation,
            context_id="sala_reuniones",
        )
        self.planner_output = PlannerOutput(
            schema_version="planner.v3",
            status="clarify",
            turn_goal="Aclarar mínimo operativo",
            decision="ask",
            content_plan=PlannerContentPlan(must_include=["pregunta útil"], must_avoid=["inventar"]),
            limits=PlannerLimits(
                max_sentences=3,
                max_questions=1,
                allow_topic_shift=False,
                allow_personal_disclosure=False,
            ),
            memory_targets=[],
            done_criteria=["aclaracion_emitida"],
        )

    def _visible_identifier_universe(self, node: str, payload: dict) -> set[str]:
        adapted = self.adapter.adapt_input_payload(node, payload)
        visible: set[str] = set()

        def walk(value: object, prefix: str = "") -> None:
            if not isinstance(value, dict):
                return
            for key, item in value.items():
                path = f"{prefix}.{key}" if prefix else key
                visible.add(key)
                visible.add(path)
                if isinstance(item, dict):
                    walk(item, path)
                elif isinstance(item, list):
                    visible.add(f"{path}[]")
                    for sub in item:
                        if isinstance(sub, dict):
                            walk(sub, f"{path}[]")

        walk(adapted)
        return visible

    def _prompt_backtick_identifiers(self, prompt_name: str) -> set[str]:
        prompt = (self.context.prompts_dir / prompt_name).read_text(encoding="utf-8")
        return set(re.findall(r"`([a-zA-Z0-9_.\\[\\]]+)`", prompt))

    def _prompt_text(self, prompt_name: str) -> str:
        return (self.context.prompts_dir / prompt_name).read_text(encoding="utf-8")

    def test_planner_prompt_uses_visible_mapping_names(self) -> None:
        planner_input = build_planner_input(
            self.canonical,
            self.recent,
            self.user_turn,
            self.trace,
            str(self.context.prompts_dir),
        )
        visible = self._visible_identifier_universe("planner", planner_input.model_dump(mode="json"))
        ids = self._prompt_backtick_identifiers("planner_prompt.txt")
        planner_prompt_text = self._prompt_text("planner_prompt.txt")

        expected_visible_refs = {
            "rol_privado_de_diego",
            "contexto_privado_del_caso",
            "fase_actual_y_reglas",
            "estado_conversacional_actual",
            "estado_negociacion_actual",
            "conversation_phase",
            "selected_memory",
            "node_task_contract",
        }
        for ref in expected_visible_refs:
            self.assertIn(ref, planner_prompt_text)
        self.assertTrue(expected_visible_refs.issubset(visible))

        legacy_mismatched_refs = {
            "diego_private_role",
            "case_private_context",
            "current_phase_guide",
            "live_conversation_state",
            "live_room_negotiation_state",
        }
        self.assertTrue(ids.isdisjoint(legacy_mismatched_refs))
        for legacy in legacy_mismatched_refs:
            self.assertNotIn(legacy, planner_prompt_text)

    def test_executor_prompt_and_payload_names_match(self) -> None:
        executor_input = build_executor_input(
            self.canonical,
            self.recent,
            self.planner_output,
            self.user_turn,
            self.trace,
            max_recent_turns=4,
            prompts_dir=str(self.context.prompts_dir),
        )
        visible = self._visible_identifier_universe("executor", executor_input.model_dump(mode="json"))
        executor_prompt_text = self._prompt_text("executor_prompt.txt")
        expected = {
            "turn_plan",
            "node_task_contract",
            "diego_voice_profile",
            "output_constraints",
            "memory_focus_targets",
        }
        for ref in expected:
            self.assertIn(ref, executor_prompt_text)
        self.assertTrue(expected.issubset(visible))
