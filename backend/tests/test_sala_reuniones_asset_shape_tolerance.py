from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sessions.state import SessionState

from negociacion.nodes.memory_node import DialogueMessage, TraceMeta, UserTurn
from negociacion.orchestration.flow_config import (
    _load_phase_cards,
    _load_phase_classifier_card,
    build_negotiation_pipeline_config,
    build_planner_input,
    run_negotiation_cognitive_turn,
)
from negociacion.state.canonical_state import (
    build_default_canonical_state,
    parse_negotiation_brief_payload,
    parse_persona_payload,
)
from negociacion.state.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode
from negociacion.traces.models import StructuredCallResult


def _fake_call_structured(*args, **kwargs) -> StructuredCallResult:
    _ = kwargs
    response_model = args[5]
    if response_model.__name__ == "MemoryOutput":
        parsed = {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": "diag", "pending_question": None, "last_turn_summary": "diag"},
            "negotiation_state": {
                "status": "active",
                "active_axes": ["agenda"],
                "last_offer_self": None,
                "last_offer_other": None,
                "tentative_agreement": None,
                "stall_state": {
                    "is_hard_stalemate": False,
                    "stalemate_reason": None,
                    "self_ultimatum_active": False,
                    "self_ultimatum_summary": None,
                },
                "blockers": [],
                "next_open_loop": None,
            },
        }
    elif response_model.__name__ == "PhaseClassifierOutput":
        parsed = {"schema_version": "phase_classifier.v1", "current_phase": "descubrimiento_y_comprension"}
    elif response_model.__name__ == "PlannerOutput":
        parsed = {
            "schema_version": "planner.v3",
            "status": "clarify",
            "turn_goal": "pedir dato mínimo",
            "decision": "ask",
            "content_plan": {"must_include": ["pregunta útil"], "must_avoid": ["inventar"]},
            "limits": {"max_sentences": 2, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
            "memory_targets": [],
            "done_criteria": ["dato_minimo"],
        }
    else:
        parsed = {
            "schema_version": "executor.v1",
            "status": "clarify",
            "spoken_text": "¿Qué margen tenéis?",
            "memory_used": [],
            "refusal_reason": None,
        }

    return StructuredCallResult(
        parsed_json=parsed,
        refusal=None,
        parse_error=None,
        exception_error=None,
        response=None,
        source=StructuredCallSource.model,
        model_called=True,
        raw_output_text=json.dumps(parsed, ensure_ascii=False),
    )


class PersonaShapeToleranceTests(unittest.TestCase):
    def test_persona_current_shape_still_parses(self) -> None:
        payload = json.loads(
            (Path(__file__).resolve().parents[1] / "negociacion" / "contexts" / "sala_reuniones" / "assets" / "persona.json").read_text(
                encoding="utf-8"
            )
        )
        persona = parse_persona_payload(payload)
        self.assertTrue(persona.policy.identidad_operativa)
        self.assertTrue(persona.expressive.voz_y_estilo)

    def test_policy_with_extra_nesting_and_reorganized_groups(self) -> None:
        payload = {
            "policy": {
                "identidad": {"operativa": "Eres Diego del Equipo B."},
                "objetivos": {"nucleo": "Conseguir acuerdo útil y justo."},
                "decision": {"criterio": "No suponer datos no dichos."},
                "disciplina": {"regla": "Cada cesión pide reciprocidad."},
                "privado": {"limites": "No revelar flexibilidad real."},
                "avance": {"principios": "Discovery antes de proponer."},
            },
            "expressive": {
                "escena": {"identidad": "Hablas como Diego."},
                "tono": {"base": "Sereno y humano."},
                "estilo": {"forma": "Breve y claro."},
                "fluidez": {"naturalidad": "No sonar robótico."},
                "huella": {"conversacional": "Firme sin brusquedad."},
            },
        }
        persona = parse_persona_payload(payload)
        self.assertIn("Diego", persona.policy.identidad_operativa)
        self.assertIn("reciprocidad", persona.policy.disciplina_negociadora.lower())
        self.assertIn("Sereno", persona.expressive.voz_y_estilo)

    def test_expressive_text_distributed_across_subblocks(self) -> None:
        payload = {
            "policy": {
                "identidad_operativa": "Rol claro",
                "objetivo_privado": "Objetivo",
                "criterio_de_decision": "Criterio",
                "disciplina_negociadora": "Disciplina",
                "limites_privados": "Límites",
                "principios_de_avance": "Avance",
            },
            "expressive": {
                "identidad": {"en_escena": "Persona concreta"},
                "marco": {"conversacional": "Contexto real"},
                "voz": {"tono_base": "Directo"},
                "estilo": {"fraseo": "Conversacional"},
                "natural": {"regla": "Naturalidad ante todo"},
                "huella": {"estampa": "Calma y criterio"},
            },
        }
        persona = parse_persona_payload(payload)
        self.assertIn("Directo", persona.expressive.voz_y_estilo)
        self.assertIn("Naturalidad", persona.expressive.naturalidad)

    def test_planner_and_executor_receive_canonical_persona_contract(self) -> None:
        state = build_default_canonical_state(session_id="s", user_id="u", thread_mode=ThreadMode.conversation, context_id="sala_reuniones")
        state.persona = parse_persona_payload(
            {
                "policy": {
                    "bloque": {
                        "identidad_operativa": "Eres Diego",
                        "objetivo_privado": "Objetivo",
                        "criterio_de_decision": "Criterio",
                        "disciplina_negociadora": "Disciplina",
                        "limites_privados": "Límites",
                        "principios_de_avance": "Avance",
                    }
                },
                "expressive": {
                    "bloque": {
                        "identidad_en_escena": "Diego en escena",
                        "marco_conversacional": "Marco",
                        "tono_base": "Sereno",
                        "estilo": "Breve",
                        "naturalidad": "Natural",
                        "huella_conversacional": "Huella",
                    }
                },
            }
        )

        user_turn = UserTurn(
            raw_text="hola",
            normalized_text="hola",
            modality="text",
            language="es",
            timestamp_iso="2026-01-01T00:00:00+00:00",
        )
        trace = TraceMeta(turn_id="t", prompt_version="p", schema_version="s", model_target="m")
        recent: list[DialogueMessage] = []
        planner_input = build_planner_input(state, recent, user_turn, trace, str(Path(__file__).resolve().parents[1] / "negociacion" / "contexts" / "sala_reuniones" / "prompts"))
        self.assertTrue(planner_input.persona_policy.identidad_operativa)
        self.assertTrue(planner_input.persona_policy.principios_de_avance)


class NegotiationBriefShapeToleranceTests(unittest.TestCase):
    def test_brief_current_shape_parses(self) -> None:
        payload = json.loads(
            (Path(__file__).resolve().parents[1] / "negociacion" / "contexts" / "sala_reuniones" / "assets" / "negotiation_brief.json").read_text(
                encoding="utf-8"
            )
        )
        brief = parse_negotiation_brief_payload(payload)
        self.assertEqual(brief.schema_version, "negotiation_brief.v1")
        self.assertGreaterEqual(len(brief.mapa_de_valor.items), 1)

    def test_brief_regrouped_with_extra_depth_and_reordered_blocks(self) -> None:
        payload = {
            "meta": {
                "brief": {
                    "contexto": {"mercado": {"valor": "Sala única 08-16", "lectura": "La mañana vale más."}},
                    "decision": {
                        "objetivo": "Acuerdo justo",
                        "criterio": "No aceptar franja peor sin compensación",
                        "realismo": "Alternativa peor",
                        "regla_tardia": "14-16 perjudica",
                    },
                    "alternativa": {
                        "resumen": "Sin acuerdo hay pérdida de calidad",
                        "detalle": "Mover fuera empeora continuidad",
                        "coste": "Coste equivalente alto",
                    },
                }
            },
            "estructura": {
                "valor": {"nota": "mapa", "items": [{"elemento": "Ayuda logística", "lectura": "suma", "tipo_de_efecto": "facilita", "valor_aproximado_eur": None}]},
                "tradeoffs": {"puede_ofrecer": [{"elemento": "Preparar antes", "uso": "reduce fricción"}]},
                "sensible": {
                    "no_revelar": ["margen interno"],
                    "lectura": "No regalar flexibilidad",
                },
            },
        }
        brief = parse_negotiation_brief_payload(payload)
        self.assertTrue(brief.contexto_de_mercado.valor_estimado)
        self.assertTrue(brief.objetivo_y_marco_de_decision.criterio)
        self.assertGreaterEqual(len(brief.monedas_de_intercambio_del_comprador.puede_ofrecer), 1)

    def test_brief_partial_missing_non_essential_sections_stays_valid(self) -> None:
        payload = {
            "solo": {
                "contexto": {"valor": "Sala única"},
                "objetivo": "Proteger núcleo",
            }
        }
        brief = parse_negotiation_brief_payload(payload)
        self.assertTrue(brief.contexto_de_mercado.valor_estimado)
        self.assertTrue(brief.realidad_de_la_alternativa.resumen)


class PhaseAssetShapeToleranceTests(unittest.TestCase):
    def test_phase_cards_current_shape_loads(self) -> None:
        prompts_dir = Path(__file__).resolve().parents[1] / "negociacion" / "contexts" / "sala_reuniones" / "prompts"
        cards = _load_phase_cards(str(prompts_dir))
        self.assertIn(NegotiationPhase.clima_humano, cards)

    def test_phase_cards_nested_groups_and_depth_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            prompts_dir = Path(td)
            payload = {
                "bundle": {
                    "cards": {
                        "descubrimiento_y_comprension": {
                            "phase": "descubrimiento_y_comprension",
                            "guidance": "Discovery primero",
                            "reglas": {"bullets": ["No proponer sin base"]},
                        },
                        "clima_humano": {
                            "phase": "clima_humano",
                            "capas": {"mensaje": {"guidance": "Natural"}},
                        },
                    }
                }
            }
            (prompts_dir / "phase_cards.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            cards = _load_phase_cards(str(prompts_dir))
            self.assertEqual(cards[NegotiationPhase.descubrimiento_y_comprension].guidance, "Discovery primero")
            self.assertEqual(cards[NegotiationPhase.clima_humano].guidance, "Fallback guidance for phase clima_humano.")

    def test_phase_cards_only_phase_name_anchor_in_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            prompts_dir = Path(td)
            payload = {
                "phases": [
                    {
                        "phase": "propuesta_creativa",
                        "meta": {"instrucciones": {"objetivo": "Una propuesta simple"}},
                        "guidance": "Proponer con reciprocidad",
                    }
                ]
            }
            (prompts_dir / "phase_cards.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            cards = _load_phase_cards(str(prompts_dir))
            self.assertEqual(cards[NegotiationPhase.propuesta_creativa].guidance, "Proponer con reciprocidad")

    def test_phase_classifier_card_nested_reorganized_shape_loads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            prompts_dir = Path(td)
            payload = {
                "wrapper": {
                    "rules": {
                        "phase_classifier_card": {
                            "purpose": "Clasificar con prudencia",
                            "deep": {"output_expectation": "JSON válido"},
                        }
                    }
                }
            }
            (prompts_dir / "phase_classifier_card.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            card, _source = _load_phase_classifier_card(str(prompts_dir))
            self.assertIn("purpose", card)


class EndToEndTraceToleranceTests(unittest.TestCase):
    def test_planner_trace_payload_keeps_canonical_contract(self) -> None:
        state = SessionState(user_id="u_shape", session_id="s_shape")
        config = build_negotiation_pipeline_config(context_id="sala_reuniones")
        with patch("negociacion.orchestration.flow_config._call_structured", _fake_call_structured):
            _, updated = run_negotiation_cognitive_turn(state, "¿Y vosotros?", config)

        traces = updated.world_state[f"{config.memory_key}_traces"]
        planner_payload = traces[-1]["nodes"]["planner"]["prompt_artifacts"]["input_payload_json"]
        planner_input = json.loads(planner_payload)

        self.assertIn("persona_policy", planner_input)
        self.assertIn("identidad_operativa", planner_input["persona_policy"])
        self.assertIn("negotiation_brief", planner_input)
        self.assertIn("objetivo_y_marco_de_decision", planner_input["negotiation_brief"])


if __name__ == "__main__":
    unittest.main()
