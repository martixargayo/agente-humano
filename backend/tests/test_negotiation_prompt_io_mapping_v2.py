from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from negociacion.contexts.prompt_io_mapping import PromptIOMappingError, load_prompt_io_adapter
from negociacion.nodes.executor_node import ExecutorOutput


class PromptIOMappingV2Tests(unittest.TestCase):
    def _write_mapping(self, payload: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "prompt_io_mapping.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_v2_nested_input_rename_and_hide(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "planner": {
                        "inputs": {
                            "user_turn.raw_text": {"rename": "mensaje_crudo"},
                            "trace_meta": {"hide": True},
                        }
                    }
                },
            }
        )
        adapter = load_prompt_io_adapter(path)
        payload = {
            "schema_version": "planner_input.v1",
            "user_turn": {"raw_text": "hola", "normalized_text": "hola"},
            "trace_meta": {"turn_id": "t"},
        }
        adapted = adapter.adapt_input_payload("planner", payload)
        self.assertNotIn("trace_meta", adapted)
        self.assertEqual(adapted["user_turn"]["mensaje_crudo"], "hola")
        self.assertNotIn("raw_text", adapted["user_turn"])

    def test_v2_nested_output_rename_schema_and_normalize(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "executor": {
                        "outputs": {
                            "spoken_text": {"output_alias": "respuesta_final"},
                        }
                    }
                },
            }
        )
        adapter = load_prompt_io_adapter(path)
        schema = adapter.output_schema("executor", ExecutorOutput)
        assert schema is not None
        self.assertIn("respuesta_final", schema["properties"])
        self.assertNotIn("spoken_text", schema["properties"])

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

    def test_v2_array_of_objects_nested_rename(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "executor": {
                        "inputs": {
                            "recent_dialogue_short[].text": {"rename": "mensaje"},
                        }
                    }
                },
            }
        )
        adapter = load_prompt_io_adapter(path)
        payload = {
            "recent_dialogue_short": [{"role": "user", "text": "uno"}, {"role": "assistant", "text": "dos"}],
        }
        adapted = adapter.adapt_input_payload("executor", payload)
        self.assertEqual(adapted["recent_dialogue_short"][0]["mensaje"], "uno")
        self.assertNotIn("text", adapted["recent_dialogue_short"][0])

    def test_v2_scalar_list_path_supported_for_field_level_rename(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "memory": {
                        "outputs": {
                            "negotiation_state.active_axes[]": {"rename": "ejes_activos"},
                        }
                    }
                },
            }
        )
        adapter = load_prompt_io_adapter(path)
        normalized = adapter.normalize_output_payload(
            "memory",
            {
                "schema_version": "memory.v1",
                "episodic_append": [],
                "working_memory_new": {"current_topic": None, "pending_question": None, "last_turn_summary": "s"},
                "negotiation_state": {"status": "inactive", "ejes_activos": ["price"], "stall_state": {"is_hard_stalemate": False, "stalemate_reason": None, "self_ultimatum_active": False, "self_ultimatum_summary": None}, "blockers": [], "next_open_loop": None, "last_offer_self": None, "last_offer_other": None, "tentative_agreement": None},
            },
        )
        self.assertEqual(normalized["negotiation_state"]["active_axes"], ["price"])


    def test_v2_output_schema_renames_nested_fields_inside_array_items(self) -> None:
        from negociacion.nodes.memory_node import MemoryOutput

        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "memory": {
                        "outputs": {
                            "episodic_append[].event_summary": {"rename": "fact_summary"}
                        }
                    }
                },
            }
        )
        adapter = load_prompt_io_adapter(path)
        schema = adapter.output_schema("memory", MemoryOutput)
        assert schema is not None

        episodic = schema["properties"]["episodic_append"]
        items = episodic["items"]
        if "$ref" in items:
            ref = items["$ref"].split("#/")[-1].split("/")
            resolved = schema
            for part in ref:
                resolved = resolved[part]
            item_props = resolved["properties"]
        else:
            item_props = items["properties"]
        self.assertIn("fact_summary", item_props)
        self.assertNotIn("event_summary", item_props)

    def test_v2_error_on_hiding_required_nested_output(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "executor": {
                        "outputs": {
                            "spoken_text": {"hide": True},
                        }
                    }
                },
            }
        )
        with self.assertRaises(PromptIOMappingError) as ctx:
            load_prompt_io_adapter(path)
        self.assertIn("cannot_hide_required_field", str(ctx.exception))

    def test_v2_error_on_unknown_path(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {"planner": {"inputs": {"user_turn.inexistente": {"rename": "x"}}}},
            }
        )
        with self.assertRaises(PromptIOMappingError) as ctx:
            load_prompt_io_adapter(path)
        self.assertIn("field_not_found", str(ctx.exception))

    def test_v2_error_on_parent_hidden_with_child_rule(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "planner": {
                        "inputs": {
                            "user_turn": {"hide": True},
                            "user_turn.raw_text": {"rename": "mensaje"},
                        }
                    }
                },
            }
        )
        with self.assertRaises(PromptIOMappingError) as ctx:
            load_prompt_io_adapter(path)
        self.assertIn("parent_hidden", str(ctx.exception))

    def test_v2_error_on_visible_collision(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "planner": {
                        "inputs": {
                            "user_turn.raw_text": {"rename": "msg"},
                            "user_turn.normalized_text": {"rename": "msg"},
                        }
                    }
                },
            }
        )
        with self.assertRaises(PromptIOMappingError) as ctx:
            load_prompt_io_adapter(path)
        self.assertIn("duplicate_visible_name", str(ctx.exception))

    def test_v2_value_aliases_declared_but_not_supported_phase1(self) -> None:
        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "executor": {
                        "outputs": {
                            "status": {"value_aliases": {"deliver": "ok"}}
                        }
                    }
                },
            }
        )
        with self.assertRaises(PromptIOMappingError) as ctx:
            load_prompt_io_adapter(path)
        self.assertIn("not_supported_in_v2_phase1", str(ctx.exception))



    def test_v2_end_to_end_turn_keeps_canonical_payload_and_renders_visible_nested_keys(self) -> None:
        from unittest.mock import patch

        from sessions.state import SessionState

        from negociacion.contexts.models import ResolvedNegotiationContext
        from negociacion.orchestration.flow_config import NegotiationTurnConfig, run_negotiation_cognitive_turn

        path = self._write_mapping(
            {
                "schema_version": "prompt_io_mapping.v2",
                "nodes": {
                    "planner": {
                        "inputs": {
                            "user_turn.raw_text": {"rename": "mensaje_crudo"},
                            "user_turn.normalized_text": {"rename": "mensaje_normalizado"},
                        },
                        "outputs": {
                            "turn_goal": {"output_alias": "objetivo_turno"}
                        },
                    }
                },
            }
        )

        context = ResolvedNegotiationContext(
            flow_id="negociacion",
            context_id="baseline_current",
            context_version="1.0.0",
            public_slug="negociacion",
            context_dir=path.parent,
            presentation_dir=path.parent,
            prompts_dir=Path("backend/negociacion/contexts/baseline_current/prompts"),
            persona_path=Path("backend/negociacion/contexts/baseline_current/assets/persona.json"),
            negotiation_brief_path=Path("backend/negociacion/contexts/baseline_current/assets/negotiation_brief.json"),
            phase_cards_path=Path("backend/negociacion/contexts/baseline_current/assets/phase_cards.json"),
            phase_classifier_card_path=Path("backend/negociacion/contexts/baseline_current/assets/phase_classifier_card.json"),
            prompt_io_mapping_path=path,
            resolution_source="official_context",
        )

        state = SessionState(session_id="s_v2", user_id="u_v2")
        config = NegotiationTurnConfig(prompts_dir="backend/negociacion/contexts/baseline_current/prompts")
        with patch("negociacion.orchestration.flow_config.resolve_context_for_prompts_dir", return_value=context):
            _, updated = run_negotiation_cognitive_turn(state, "Hola", config)

        trace = updated.world_state["negotiation_canonical_traces"][-1]["nodes"]["planner"]["prompt_artifacts"]
        prompt_rendered = trace["user_prompt_rendered"]
        canonical_payload = trace["input_payload_json"]

        self.assertIn("mensaje_crudo", prompt_rendered)
        self.assertNotIn('"raw_text"', prompt_rendered)
        self.assertIn('"raw_text"', canonical_payload)

if __name__ == "__main__":
    unittest.main()
