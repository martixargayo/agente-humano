from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sessions.state import SessionState

from negociacion.contexts.models import ResolvedNegotiationContext
from negociacion.contexts.prompt_io_mapping import PromptIOMappingError, load_prompt_io_adapter
from negociacion.nodes.memory_node import TraceMeta, UserTurn
from negociacion.orchestration.flow_config import (
    NegotiationTurnConfig,
    _adapt_payload_json_for_prompt,
    build_planner_input,
    run_negotiation_cognitive_turn,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import ThreadMode


class NegotiationPromptIOMappingTests(unittest.TestCase):
    def _planner_payload(self) -> dict[str, object]:
        canonical = build_default_canonical_state(session_id="s", user_id="u", thread_mode=ThreadMode.conversation)
        user_turn = UserTurn(
            raw_text="hola",
            normalized_text="hola",
            modality="text",
            language="es",
            timestamp_iso="2026-03-30T00:00:00+00:00",
        )
        trace = TraceMeta(
            turn_id="t1",
            prompt_version="planner_v3",
            schema_version="planner_input.v1",
            model_target="gpt-5-nano",
        )
        planner_input = build_planner_input(canonical, [], user_turn, trace, "backend/negociacion/contexts/baseline_current/prompts")
        return planner_input.model_dump(mode="json")

    def test_context_without_mapping_keeps_identity_behavior(self) -> None:
        adapter = load_prompt_io_adapter(None)
        payload = self._planner_payload()
        self.assertEqual(adapter.adapt_input_payload("planner", payload), payload)

    def test_rename_input_for_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt_io_mapping.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "planner": {
                                "inputs": {
                                    "persona_policy": {"rename": "rol_privado"}
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            adapter = load_prompt_io_adapter(path)
            payload = self._planner_payload()
            adapted = adapter.adapt_input_payload("planner", payload)
            self.assertIn("rol_privado", adapted)
            self.assertNotIn("persona_policy", adapted)

    def test_hide_input_for_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt_io_mapping.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "planner": {
                                "inputs": {
                                    "phase_card": {"hide": True}
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            adapter = load_prompt_io_adapter(path)
            payload = self._planner_payload()
            adapted = adapter.adapt_input_payload("planner", payload)
            self.assertNotIn("phase_card", adapted)

    def test_rename_output_for_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt_io_mapping.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "executor": {
                                "outputs": {
                                    "spoken_text": {"output_alias": "respuesta_final"}
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            adapter = load_prompt_io_adapter(path)
            normalized = adapter.normalize_output_payload(
                "executor",
                {
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "respuesta_final": "ok",
                    "memory_used": [],
                    "refusal_reason": None,
                },
            )
            self.assertEqual(normalized["spoken_text"], "ok")
            self.assertNotIn("respuesta_final", normalized)

    def test_multiple_aliases_same_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt_io_mapping.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "planner": {
                                "inputs": {
                                    "persona_policy": {"rename": "rol_privado"},
                                    "negotiation_brief": {"rename": "marco_del_caso"},
                                    "phase_card": {"hide": True},
                                }
                            },
                            "executor": {
                                "outputs": {
                                    "spoken_text": {"output_alias": "respuesta_final"}
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            adapter = load_prompt_io_adapter(path)
            payload_json = json.dumps(self._planner_payload(), ensure_ascii=False)
            adapted_json = _adapt_payload_json_for_prompt(adapter, "planner", payload_json)
            adapted = json.loads(adapted_json)
            self.assertIn("rol_privado", adapted)
            self.assertIn("marco_del_caso", adapted)
            self.assertNotIn("phase_card", adapted)

    def test_invalid_mapping_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt_io_mapping.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "planner": {
                                "inputs": {
                                    "persona_policy": {"rename": "dup"},
                                    "negotiation_brief": {"rename": "dup"},
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PromptIOMappingError) as ctx:
                load_prompt_io_adapter(path)
            self.assertIn("duplicate_visible_input_name", str(ctx.exception))

    def test_end_to_end_real_turn_uses_visible_aliases_but_keeps_internal_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mapping_path = tmp_path / "prompt_io_mapping.json"
            mapping_path.write_text(
                json.dumps(
                    {
                        "schema_version": "prompt_io_mapping.v1",
                        "nodes": {
                            "planner": {
                                "inputs": {
                                    "persona_policy": {"rename": "rol_privado"},
                                    "negotiation_brief": {"rename": "marco_del_caso"},
                                    "phase_card": {"hide": True},
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            context = ResolvedNegotiationContext(
                flow_id="negociacion",
                context_id="baseline_current",
                context_version="1.0.0",
                public_slug="negociacion",
                context_dir=tmp_path,
                presentation_dir=tmp_path,
                prompts_dir=Path("backend/negociacion/contexts/baseline_current/prompts"),
                persona_path=Path("backend/negociacion/contexts/baseline_current/assets/persona.json"),
                negotiation_brief_path=Path("backend/negociacion/contexts/baseline_current/assets/negotiation_brief.json"),
                phase_cards_path=Path("backend/negociacion/contexts/baseline_current/assets/phase_cards.json"),
                phase_classifier_card_path=Path("backend/negociacion/contexts/baseline_current/assets/phase_classifier_card.json"),
                prompt_io_mapping_path=mapping_path,
                resolution_source="official_context",
            )

            state = SessionState(session_id="s_alias", user_id="u_alias")
            config = NegotiationTurnConfig(prompts_dir="backend/negociacion/contexts/baseline_current/prompts")
            with patch("negociacion.orchestration.flow_config.resolve_context_for_prompts_dir", return_value=context):
                reply, updated = run_negotiation_cognitive_turn(state, "Hola", config)

            traces = updated.world_state["negotiation_canonical_traces"]
            planner_prompt = traces[-1]["nodes"]["planner"]["prompt_artifacts"]["user_prompt_rendered"]
            planner_payload = traces[-1]["nodes"]["planner"]["prompt_artifacts"]["input_payload_json"]

            self.assertIsInstance(reply, str)
            self.assertIn("rol_privado", planner_prompt)
            self.assertIn("marco_del_caso", planner_prompt)
            self.assertNotIn('"phase_card"', planner_prompt)
            self.assertIn('"phase_card"', planner_payload)


if __name__ == "__main__":
    unittest.main()
