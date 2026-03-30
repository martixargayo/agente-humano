from __future__ import annotations

import json
import unittest

from sessions.state import SessionState

from negociacion.contexts import resolve_negotiation_context
from negociacion.contexts.prompt_io_mapping import load_prompt_io_adapter
from negociacion.nodes.executor_node import ExecutorOutput
from negociacion.orchestration.flow_config import _call_structured, build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from negociacion.state.shared_types import StructuredCallSource


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.refusal = None


class _FakeResponsesClient:
    def __init__(self, output_text: str):
        self._output_text = output_text
        self.responses = self

    def create(self, **kwargs):
        _ = kwargs
        return _FakeResponse(self._output_text)


class SalaReunionesPromptIOMappingTests(unittest.TestCase):
    def test_sala_reuniones_context_loads_prompt_io_mapping_file(self) -> None:
        context = resolve_negotiation_context("sala_reuniones")
        self.assertIsNotNone(context.prompt_io_mapping_path)
        self.assertTrue(context.prompt_io_mapping_path.exists())

    def test_sala_reuniones_prompt_render_uses_contextual_aliases_and_hides_fields(self) -> None:
        state = SessionState(user_id="u_sala", session_id="s_sala")
        config = build_negotiation_pipeline_config(context_id="sala_reuniones")

        _, updated_state = run_negotiation_cognitive_turn(state, "Necesitamos coordinar la sala demo para mañana.", config)

        traces = updated_state.world_state[f"{config.memory_key}_traces"]
        planner_artifacts = traces[-1]["nodes"]["planner"]["prompt_artifacts"]
        rendered = planner_artifacts["user_prompt_rendered"]
        canonical_payload = planner_artifacts["input_payload_json"]

        self.assertIn('"rol_privado_de_diego"', rendered)
        self.assertIn('"contexto_privado_del_caso"', rendered)
        self.assertIn('"fase_actual_y_reglas"', rendered)
        self.assertIn('"estado_conversacional_actual"', rendered)
        self.assertIn('"estado_negociacion_actual"', rendered)
        self.assertNotIn('"selected_memory"', rendered)
        self.assertNotIn('"trace_meta"', rendered)

        self.assertIn('"selected_memory"', canonical_payload)
        self.assertIn('"trace_meta"', canonical_payload)

    def test_sala_reuniones_executor_output_alias_is_normalized_to_canonical(self) -> None:
        context = resolve_negotiation_context("sala_reuniones")
        adapter = load_prompt_io_adapter(context.prompt_io_mapping_path)
        fake_client = _FakeResponsesClient(
            json.dumps(
                {
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "respuesta_final": "Confirmado: avanzamos con la coordinación de sala.",
                    "memory_used": [],
                    "refusal_reason": None,
                },
                ensure_ascii=False,
            )
        )

        result = _call_structured(
            fake_client,
            "gpt-5-nano",
            [{"role": "user", "content": "test"}],
            "executor",
            adapter,
            ExecutorOutput,
            "low",
            {},
            False,
        )

        self.assertEqual(result.source, StructuredCallSource.model)
        assert result.parsed_json is not None
        self.assertEqual(result.parsed_json["spoken_text"], "Confirmado: avanzamos con la coordinación de sala.")
        self.assertNotIn("respuesta_final", result.parsed_json)


if __name__ == "__main__":
    unittest.main()
