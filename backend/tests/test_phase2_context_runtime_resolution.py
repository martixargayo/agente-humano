from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from negociacion.contexts import resolve_default_negotiation_context, resolve_negotiation_context
from negociacion.orchestration.flow_config import (
    NEGOTIATION_FLOW_DETAILS,
    _load_phase_cards,
    _load_phase_classifier_card,
    build_negotiation_pipeline_config,
)
from negociacion.state.canonical_state import CanonicalState, build_default_canonical_state, parse_negotiation_brief_payload
from negociacion.state.shared_types import NegotiationPhase, ThreadMode

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
BASELINE_DIR = BACKEND_DIR / "negociacion" / "contexts" / "baseline_current"
LEGACY_PROMPTS_DIR = BACKEND_DIR / "negociacion" / "prompts"


class Phase2ContextRuntimeResolutionTests(unittest.TestCase):
    def test_resolver_returns_official_baseline_paths(self) -> None:
        ctx = resolve_default_negotiation_context()
        self.assertEqual(ctx.context_id, "baseline_current")
        self.assertEqual(ctx.prompts_dir, BASELINE_DIR / "prompts")
        self.assertEqual(ctx.persona_path, BASELINE_DIR / "assets" / "persona.json")
        self.assertEqual(ctx.negotiation_brief_path, BASELINE_DIR / "assets" / "negotiation_brief.json")
        self.assertEqual(ctx.phase_cards_path, BASELINE_DIR / "assets" / "phase_cards.json")
        self.assertEqual(ctx.phase_classifier_card_path, BASELINE_DIR / "assets" / "phase_classifier_card.json")
        self.assertEqual(ctx.resolution_source, "official_context")

    def test_pipeline_config_uses_resolved_official_prompts_dir_without_changing_baseline_flags(self) -> None:
        config = build_negotiation_pipeline_config()
        self.assertEqual(Path(config.prompts_dir), BASELINE_DIR / "prompts")
        self.assertEqual(config.memory_key, NEGOTIATION_FLOW_DETAILS["memory_key"])
        self.assertEqual(config.model_memory, NEGOTIATION_FLOW_DETAILS["model_memory"])
        self.assertEqual(config.model_phase_classifier, NEGOTIATION_FLOW_DETAILS["model_phase_classifier"])
        self.assertEqual(config.model_planner, NEGOTIATION_FLOW_DETAILS["model_planner"])
        self.assertEqual(config.model_executor, NEGOTIATION_FLOW_DETAILS["model_executor"])
        self.assertEqual(config.max_recent_messages, NEGOTIATION_FLOW_DETAILS["max_recent_messages"])
        self.assertEqual(config.max_executor_recent_turns, NEGOTIATION_FLOW_DETAILS["max_executor_recent_turns"])

    def test_phase_assets_are_loaded_from_official_baseline_assets_dir(self) -> None:
        ctx = resolve_default_negotiation_context()
        sample_phase = NegotiationPhase.clima_humano

        phase_cards = _load_phase_cards(str(ctx.prompts_dir))
        self.assertIn(sample_phase, phase_cards)

        phase_classifier_card, phase_classifier_card_source = _load_phase_classifier_card(str(ctx.prompts_dir))
        self.assertTrue(phase_classifier_card_source.endswith("backend/negociacion/contexts/baseline_current/assets/phase_classifier_card.json"))
        self.assertEqual(
            Path(phase_classifier_card_source),
            BASELINE_DIR / "assets" / "phase_classifier_card.json",
        )

        expected_phase_cards_raw = json.loads((BASELINE_DIR / "assets" / "phase_cards.json").read_text(encoding="utf-8"))
        self.assertEqual(
            phase_cards[sample_phase].as_dict()["phase_objective"],
            expected_phase_cards_raw[sample_phase.value]["phase_objective"],
        )

    def test_phase_assets_fallback_to_legacy_when_official_baseline_resolution_fails(self) -> None:
        fallback_ctx = resolve_negotiation_context(baseline_dir=BASELINE_DIR.parent / "__missing_baseline_for_test__")
        sample_phase = NegotiationPhase.clima_humano

        with patch(
            "negociacion.orchestration.flow_config.resolve_default_negotiation_context",
            return_value=fallback_ctx,
        ):
            phase_cards = _load_phase_cards(str(fallback_ctx.prompts_dir))
            phase_classifier_card, phase_classifier_card_source = _load_phase_classifier_card(str(fallback_ctx.prompts_dir))

        legacy_phase_cards_raw = json.loads((LEGACY_PROMPTS_DIR / "phase_cards.json").read_text(encoding="utf-8"))
        legacy_phase_classifier_card = json.loads((LEGACY_PROMPTS_DIR / "phase_classifier_card.json").read_text(encoding="utf-8"))
        self.assertEqual(
            phase_cards[sample_phase].as_dict()["phase_objective"],
            legacy_phase_cards_raw[sample_phase.value]["phase_objective"],
        )
        self.assertEqual(phase_classifier_card, legacy_phase_classifier_card)
        self.assertEqual(Path(phase_classifier_card_source), LEGACY_PROMPTS_DIR / "phase_classifier_card.json")

    def test_canonical_state_defaults_stay_logically_equal_to_legacy_baseline(self) -> None:
        state = build_default_canonical_state(session_id="s", user_id="u", thread_mode=ThreadMode.conversation)
        legacy_persona = json.loads((LEGACY_PROMPTS_DIR / "persona.json").read_text(encoding="utf-8"))
        legacy_brief = json.loads((LEGACY_PROMPTS_DIR / "negotiation_brief.json").read_text(encoding="utf-8"))
        self.assertEqual(state.persona.model_dump(mode="json"), legacy_persona)
        expected_brief = parse_negotiation_brief_payload(legacy_brief).model_dump(mode="json", exclude_none=True)
        self.assertEqual(state.negotiation_brief.model_dump(mode="json", exclude_none=True), expected_brief)

    def test_resolver_has_explicit_legacy_fallback_when_official_baseline_is_unavailable(self) -> None:
        missing_dir = BASELINE_DIR.parent / "__missing_baseline_for_test__"
        ctx = resolve_negotiation_context(baseline_dir=missing_dir)
        self.assertEqual(ctx.resolution_source, "legacy_fallback")
        self.assertEqual(ctx.prompts_dir, LEGACY_PROMPTS_DIR)
        self.assertEqual(ctx.persona_path, LEGACY_PROMPTS_DIR / "persona.json")
        self.assertEqual(ctx.negotiation_brief_path, LEGACY_PROMPTS_DIR / "negotiation_brief.json")
        self.assertEqual(ctx.phase_cards_path, LEGACY_PROMPTS_DIR / "phase_cards.json")
        self.assertEqual(ctx.phase_classifier_card_path, LEGACY_PROMPTS_DIR / "phase_classifier_card.json")

    def test_canonical_state_shape_remains_unchanged(self) -> None:
        expected_fields = {
            "session",
            "openai_thread",
            "persona",
            "negotiation_brief",
            "memory_episodic",
            "memory_working",
            "negotiation_state",
            "planner_state",
            "scene_state",
            "ui_state",
            "trace",
        }
        self.assertEqual(set(CanonicalState.model_fields.keys()), expected_fields)
        self.assertNotIn("context_id", CanonicalState.model_fields)
        self.assertNotIn("context_version", CanonicalState.model_fields)


if __name__ == "__main__":
    unittest.main()
