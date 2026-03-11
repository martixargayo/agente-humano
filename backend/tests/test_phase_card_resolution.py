from __future__ import annotations

from negociacion.orchestration.flow_config import _load_phase_cards
from negociacion.state.shared_types import NegotiationPhase


def test_load_phase_cards_returns_full_cards_for_all_phases():
    cards = _load_phase_cards("backend/negociacion/prompts")

    assert set(cards.keys()) == set(NegotiationPhase)
    clima = cards[NegotiationPhase.clima_humano].model_dump(mode="json")
    assert clima["phase"] == "clima_humano"
    assert "phase_objective" in clima
    assert "what_good_progress_looks_like" in clima
    assert "planner_bias" in clima
    assert "good_moves" in clima
    assert "avoid" in clima
    assert "question_policy" in clima
    assert "done_signals" in clima


def test_load_phase_cards_supports_other_phase_without_placeholder_only_payload():
    cards = _load_phase_cards("backend/negociacion/prompts")

    formalizacion = cards[NegotiationPhase.formalizacion_del_acuerdo].model_dump(mode="json")
    assert formalizacion["phase"] == "formalizacion_del_acuerdo"
    assert "phase_objective" in formalizacion
    assert "good_moves" in formalizacion
    assert "avoid" in formalizacion
    assert formalizacion.get("guidance")


def test_load_phase_cards_supports_abandono_phase():
    cards = _load_phase_cards("backend/negociacion/prompts")

    abandono = cards[NegotiationPhase.abandono_de_la_negociacion].model_dump(mode="json")
    assert abandono["phase"] == "abandono_de_la_negociacion"
    assert "phase_objective" in abandono
    assert "good_moves" in abandono
    assert "avoid" in abandono
    assert abandono.get("guidance")
