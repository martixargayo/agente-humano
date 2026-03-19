from __future__ import annotations

import json
from pathlib import Path

from negociacion.contexts import resolve_default_negotiation_context, resolve_negotiation_context
from negociacion.orchestration.flow_config import (
    _load_phase_cards,
    _load_phase_classifier_card,
    build_negotiation_pipeline_config,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, ThreadMode

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
LEGACY_PROMPTS_DIR = BACKEND_DIR / "negociacion" / "prompts"
BASELINE_DIR = BACKEND_DIR / "negociacion" / "contexts" / "baseline_current"


def main() -> None:
    official = resolve_default_negotiation_context()
    sample_phase = NegotiationPhase.clima_humano
    print("[official_context]")
    print(f"context_id={official.context_id}")
    print(f"resolution_source={official.resolution_source}")
    print(f"prompts_dir={official.prompts_dir}")
    print(f"persona_path={official.persona_path}")
    print(f"negotiation_brief_path={official.negotiation_brief_path}")
    print(f"phase_cards_path={official.phase_cards_path}")
    print(f"phase_classifier_card_path={official.phase_classifier_card_path}")

    config = build_negotiation_pipeline_config()
    phase_cards = _load_phase_cards(str(config.prompts_dir))
    phase_classifier_card, phase_classifier_card_source = _load_phase_classifier_card(str(config.prompts_dir))
    print("\n[runtime_config]")
    print(f"prompts_dir={config.prompts_dir}")
    print(f"prompts_dir_matches_official={Path(config.prompts_dir) == BASELINE_DIR / 'prompts'}")
    print(f"phase_cards_source={official.phase_cards_path}")
    print(f"phase_cards_{sample_phase.value}_matches_official={phase_cards[sample_phase].as_dict()['phase_objective'] == json.loads(official.phase_cards_path.read_text(encoding='utf-8'))[sample_phase.value]['phase_objective']}")
    print(f"phase_classifier_card_source={phase_classifier_card_source}")
    print(f"phase_classifier_card_matches_official={phase_classifier_card == json.loads(official.phase_classifier_card_path.read_text(encoding='utf-8'))}")

    state = build_default_canonical_state(session_id="s", user_id="u", thread_mode=ThreadMode.conversation)
    legacy_persona = json.loads((LEGACY_PROMPTS_DIR / "persona.json").read_text(encoding="utf-8"))
    legacy_brief = json.loads((LEGACY_PROMPTS_DIR / "negotiation_brief.json").read_text(encoding="utf-8"))
    print("\n[state_defaults]")
    print(f"persona_matches_legacy={state.persona.model_dump(mode='json') == legacy_persona}")
    print(f"negotiation_brief_matches_legacy={state.negotiation_brief.model_dump(mode='json') == legacy_brief}")

    fallback = resolve_negotiation_context(baseline_dir=BASELINE_DIR.parent / "__missing_baseline_for_check__")
    print("\n[legacy_fallback]")
    print(f"resolution_source={fallback.resolution_source}")
    print(f"prompts_dir={fallback.prompts_dir}")
    print(f"persona_path={fallback.persona_path}")
    print(f"negotiation_brief_path={fallback.negotiation_brief_path}")
    print(f"phase_cards_path={fallback.phase_cards_path}")
    print(f"phase_classifier_card_path={fallback.phase_classifier_card_path}")

    print("\nresultado=ok")


if __name__ == "__main__":
    main()
