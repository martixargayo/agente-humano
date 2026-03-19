from __future__ import annotations

import json
from pathlib import Path

from evaluacion.domains.negotiation.assets_loader import resolve_negotiation_evaluation_assets
from evaluacion.domains.negotiation.extractor import build_feedback_input_bundle_v1
from evaluacion.domains.negotiation.rubric_loader import load_negotiation_rubric_v1
from negociacion.contexts import resolve_default_negotiation_context
from sessions.state import SESSIONS, SessionState, get_session_state
from interfaz_usuario.services import ensure_session

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_CORE_PROMPT = REPO_ROOT / 'backend' / 'evaluacion' / 'prompts' / 'core_evaluator_prompt.txt'
LEGACY_TRAJECTORY_PROMPT = REPO_ROOT / 'backend' / 'evaluacion' / 'prompts' / 'trajectory_evaluator_prompt.txt'
LEGACY_RUBRIC = REPO_ROOT / 'backend' / 'evaluacion' / 'domains' / 'negotiation' / 'rubrics' / 'negotiation_rubric_v1.json'


def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas, dime'},
    ]


def main() -> None:
    SESSIONS.clear()
    ensure_session(user_id='u_phase6', session_id='s_phase6')
    state = get_session_state(user_id='u_phase6', session_id='s_phase6')
    _seed_history(state)

    bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-phase6')
    assets = resolve_negotiation_evaluation_assets(bundle.domain_context)
    rubric = load_negotiation_rubric_v1(bundle.domain_context)

    print('[resolved_bundle_context]')
    print(bundle.domain_context.model_dump(mode='json'))
    print('\n[resolved_core_prompt]')
    print({'path': str(assets.core_prompt_path), 'matches_legacy': assets.core_prompt_path.read_text(encoding='utf-8') == LEGACY_CORE_PROMPT.read_text(encoding='utf-8')})
    print('\n[resolved_trajectory_prompt]')
    print({'path': str(assets.trajectory_prompt_path), 'matches_legacy': assets.trajectory_prompt_path.read_text(encoding='utf-8') == LEGACY_TRAJECTORY_PROMPT.read_text(encoding='utf-8')})
    print('\n[resolved_rubric]')
    print({'path': str(assets.rubric_path), 'matches_legacy': rubric.model_dump(mode='json') == json.loads(LEGACY_RUBRIC.read_text(encoding='utf-8'))})

    legacy_state = SessionState(user_id='u_phase6_legacy', session_id='s_phase6_legacy')
    _seed_history(legacy_state)
    SESSIONS[('u_phase6_legacy', 's_phase6_legacy')] = legacy_state
    legacy_bundle = build_feedback_input_bundle_v1(state=legacy_state, evaluation_id='eval-phase6-legacy')
    print('\n[legacy_fallback_bundle_context]')
    print(legacy_bundle.domain_context.model_dump(mode='json'))
    print('\nresultado=ok')


if __name__ == '__main__':
    main()
