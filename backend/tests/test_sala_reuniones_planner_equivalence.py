from __future__ import annotations

import json
import re
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from negociacion.nodes.memory_node import DialogueMessage, TraceMeta, UserTurn
from negociacion.orchestration.flow_config import build_phase_input, build_planner_input
from negociacion.state.canonical_state import (
    CanonicalState,
    parse_negotiation_brief_payload,
    parse_persona_payload,
    build_default_canonical_state,
)
from negociacion.state.shared_types import NegotiationPhase, ThreadMode

ROOT = Path(__file__).resolve().parents[1]
SALA = ROOT / "negociacion" / "contexts" / "sala_reuniones"


def _tok(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9áéíóúñ]+", value.lower()) if t}


def _overlap(a: str, b: str) -> float:
    ta = _tok(a)
    tb = _tok(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


@dataclass(frozen=True)
class Case:
    name: str
    phase: NegotiationPhase
    user: str
    recent: tuple[str, ...] = ()


CASES = [
    Case("saludo_puro", NegotiationPhase.clima_humano, "hola"),
    Case("apertura_conflicto", NegotiationPhase.descubrimiento_y_comprension, "Tenemos conflicto por la sala del jueves"),
    Case("y_vosotros", NegotiationPhase.descubrimiento_y_comprension, "Nosotros necesitamos 4 horas, ¿y vosotros?"),
    Case("cuanto_necesitais", NegotiationPhase.descubrimiento_y_comprension, "¿Cuánto necesitáis vosotros?"),
    Case("composicion_5_horas", NegotiationPhase.descubrimiento_y_comprension, "¿Y esas 5 horas en qué se os van?"),
    Case("franja_peor", NegotiationPhase.concesiones_y_ajuste_final, "Si vosotros vais de 14 a 16, os ayudamos 10 minutos y listo"),
    Case("ajuste_vivo", NegotiationPhase.concesiones_y_ajuste_final, "Si vosotros nos dejáis 8-11, nosotros os dejamos sala montada"),
    Case("acuerdo_claro", NegotiationPhase.formalizacion_del_acuerdo, "Perfecto, entonces queda cerrado así"),
]


def _shadow_planner(planner_input: dict) -> tuple[str, str]:
    text = (planner_input["user_turn"]["normalized_text"] or "").lower()
    phase = planner_input["current_phase"]
    policy = planner_input["persona_policy"]

    if phase == "clima_humano" and text.strip() in {"hola", "buenas", "hola!"}:
        return ("hold", "saludo_breve")
    if "¿y vosotros" in text or "y vosotros" in text:
        return ("ask", "mapa_operativo_no_reparto")
    if "cuánto necesitáis" in text or "cuanto necesitais" in text:
        return ("ask", "referencia_general_5h")
    if "5 horas en qué" in text or "5 horas en que" in text:
        return ("ask", "permite_desglose")
    if "14" in text or "franja" in text:
        return ("hold", "resistencia_franja_peor")
    if "si vosotros" in text and "nosotros" in text:
        return ("counter", "ajuste_vivo_reciproco")
    if "cerrado" in text or "queda" in text:
        return ("close", "confirmacion_breve")

    # default discovery bias if policy keeps progression/discovery cues
    bias = (policy.get("principios_de_avance", "") + " " + policy.get("disciplina_negociadora", "")).lower()
    if "discovery" in bias or "aclar" in bias or "no" in bias:
        return ("ask", "discovery_primero")
    return ("counter", "degradado")


class PlannerBehaviorEquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_persona = json.loads((SALA / "assets" / "persona.json").read_text(encoding="utf-8"))
        self.base_brief = json.loads((SALA / "assets" / "negotiation_brief.json").read_text(encoding="utf-8"))
        self.base_prompts = SALA / "prompts"

    def _variant_persona(self) -> dict:
        p = self.base_persona
        return {
            "policy": {
                "identidad": {"rol": p["policy"]["identidad_operativa"]},
                "decision": {
                    "objetivo": p["policy"]["objetivo_privado"],
                    "criterio": p["policy"]["criterio_de_decision"],
                },
                "negociacion": {
                    "disciplina": p["policy"]["disciplina_negociadora"],
                    "limites": p["policy"]["limites_privados"],
                    "progresion": p["policy"].get("principios_de_avance", p["policy"].get("regla_de_progresion", "")),
                },
            },
            "expressive": {
                "escena": {"identidad": p["expressive"]["identidad_en_escena"]},
                "estilo": {
                    "marco": p["expressive"].get("marco_conversacional", ""),
                    "tono": p["expressive"].get("tono_base", p["expressive"].get("voz_y_estilo", "")),
                    "forma": p["expressive"].get("estilo", ""),
                },
                "flujo": {
                    "naturalidad": p["expressive"]["naturalidad"],
                    "huella": p["expressive"].get("huella_conversacional", p["expressive"].get("discrepancia", "")),
                },
            },
        }

    def _variant_brief(self) -> dict:
        b = self.base_brief
        return {
            "organizacion": {
                "mercado": {"data": b.get("contexto_del_recurso", b.get("contexto_de_mercado", {}))},
                "objetivo": b.get("objetivo_del_equipo_b", b.get("objetivo_y_marco_de_decision", {})),
                "restricciones": b.get("restricciones_duras", b.get("restricciones", {})),
            },
            "valor": {
                "mapa": b.get("mapa_de_valor", {}),
                "tradeoffs": b.get("monedas_de_intercambio_del_equipo_b", b.get("monedas_de_intercambio_del_comprador", {})),
            },
            "sensibles": b.get("informacion_privada_sensible", {}),
        }

    def _variant_phase_cards(self) -> dict:
        raw = json.loads((SALA / "assets" / "phase_cards.json").read_text(encoding="utf-8"))
        return {
            "catalogo": {
                "grupo_a": {
                    k: {"meta": {"nested": v}, "phase": v.get("phase", k), "guidance": v.get("guidance")}
                    for k, v in raw.items()
                }
            }
        }

    def _variant_phase_classifier_card(self) -> dict:
        raw = json.loads((SALA / "assets" / "phase_classifier_card.json").read_text(encoding="utf-8"))
        return {"wrappers": {"x": {"phase_classifier_card": raw.get("phase_classifier_card", raw)}}}

    def _build_state(self, persona_payload: dict, brief_payload: dict) -> CanonicalState:
        state = build_default_canonical_state(session_id="s", user_id="u", thread_mode=ThreadMode.conversation, context_id="sala_reuniones")
        state.persona = parse_persona_payload(persona_payload)
        state.negotiation_brief = parse_negotiation_brief_payload(brief_payload)
        return state

    def _planner_input_for_case(self, state: CanonicalState, case: Case, prompts_dir: Path) -> dict:
        state.planner_state.current_phase = case.phase
        user_turn = UserTurn(
            raw_text=case.user,
            normalized_text=case.user,
            modality="text",
            language="es",
            timestamp_iso="2026-01-01T00:00:00+00:00",
        )
        trace = TraceMeta(turn_id=f"t-{case.name}", prompt_version="planner_v3", schema_version="planner_input.v1", model_target="o4-mini")
        recent = [DialogueMessage(role="user", text=text) for text in case.recent]
        return build_planner_input(state, recent, user_turn, trace, str(prompts_dir)).model_dump(mode="json")

    def test_persona_and_brief_canonical_equivalence_is_materially_preserved(self) -> None:
        base_persona = parse_persona_payload(self.base_persona)
        var_persona = parse_persona_payload(self._variant_persona())
        self.assertGreaterEqual(_overlap(base_persona.policy.identidad_operativa, var_persona.policy.identidad_operativa), 0.40)
        self.assertGreaterEqual(_overlap(base_persona.policy.disciplina_negociadora, var_persona.policy.disciplina_negociadora), 0.35)
        self.assertGreaterEqual(_overlap(base_persona.expressive.voz_y_estilo, var_persona.expressive.voz_y_estilo), 0.25)

        base_brief = parse_negotiation_brief_payload(self.base_brief)
        var_brief = parse_negotiation_brief_payload(self._variant_brief())
        self.assertGreaterEqual(_overlap(base_brief.contexto_de_mercado.valor_estimado, var_brief.contexto_de_mercado.valor_estimado), 0.2)
        self.assertGreaterEqual(_overlap(base_brief.objetivo_y_marco_de_decision.criterio, var_brief.objetivo_y_marco_de_decision.criterio), 0.2)
        self.assertGreaterEqual(len(var_brief.mapa_de_valor.items), 1)

    def test_phase_assets_with_wrappers_still_feed_pipeline_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "phase_cards.json").write_text(json.dumps(self._variant_phase_cards(), ensure_ascii=False), encoding="utf-8")
            (p / "phase_classifier_card.json").write_text(json.dumps(self._variant_phase_classifier_card(), ensure_ascii=False), encoding="utf-8")

            state = self._build_state(self.base_persona, self.base_brief)
            state.planner_state.current_phase = NegotiationPhase.descubrimiento_y_comprension
            user_turn = UserTurn(raw_text="hola", normalized_text="hola", modality="text", language="es", timestamp_iso="2026-01-01T00:00:00+00:00")
            trace = TraceMeta(turn_id="t", prompt_version="phase_classifier_v1", schema_version="phase_classifier_input.v1", model_target="gpt-5-nano")
            phase_input = build_phase_input(state, [], user_turn, trace, str(p))
            self.assertTrue(isinstance(phase_input.phase_classifier_card, dict) and phase_input.phase_classifier_card)

            planner_input = self._planner_input_for_case(state, CASES[1], p)
            self.assertEqual(planner_input["phase_card"]["phase"], "descubrimiento_y_comprension")

    def test_planner_tactical_behavior_equivalence_across_structural_variants(self) -> None:
        base_state = self._build_state(self.base_persona, self.base_brief)
        var_state = self._build_state(self._variant_persona(), self._variant_brief())

        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "phase_cards.json").write_text(json.dumps(self._variant_phase_cards(), ensure_ascii=False), encoding="utf-8")
            (p / "phase_classifier_card.json").write_text(json.dumps(self._variant_phase_classifier_card(), ensure_ascii=False), encoding="utf-8")

            for case in CASES:
                base_input = self._planner_input_for_case(base_state, case, self.base_prompts)
                var_input = self._planner_input_for_case(var_state, case, p)
                self.assertEqual(
                    _shadow_planner(base_input),
                    _shadow_planner(var_input),
                    msg=f"planner_behavior_drift case={case.name}",
                )


if __name__ == "__main__":
    unittest.main()
