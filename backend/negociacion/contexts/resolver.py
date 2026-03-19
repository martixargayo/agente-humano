from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ResolvedNegotiationContext

_CONTEXTS_DIR = Path(__file__).resolve().parent
_BASELINE_CONTEXT_DIR = _CONTEXTS_DIR / 'baseline_current'
_LEGACY_PROMPTS_DIR = _CONTEXTS_DIR.parent / 'prompts'
_DEFAULT_FLOW_ID = 'negociacion'
_DEFAULT_CONTEXT_ID = 'baseline_current'
_DEFAULT_CONTEXT_VERSION = '1.0.0'
_DEFAULT_PUBLIC_SLUG = 'negociacion'


class NegotiationContextResolutionError(RuntimeError):
    pass


def resolve_default_negotiation_context(*, baseline_dir: Path | None = None) -> ResolvedNegotiationContext:
    return resolve_negotiation_context(context_id=_DEFAULT_CONTEXT_ID, baseline_dir=baseline_dir)


def resolve_negotiation_context(
    context_id: str | None = None,
    *,
    baseline_dir: Path | None = None,
) -> ResolvedNegotiationContext:
    requested_context_id = (context_id or _DEFAULT_CONTEXT_ID).strip() or _DEFAULT_CONTEXT_ID
    candidate_dir = baseline_dir or _resolve_context_dir(requested_context_id)
    if candidate_dir is None:
        raise NegotiationContextResolutionError(f'unsupported_negotiation_context:{requested_context_id}')

    manifest_path = candidate_dir / 'manifest.json'
    official_context = _build_official_context(candidate_dir, manifest_path)
    if official_context is not None:
        return official_context

    if requested_context_id == _DEFAULT_CONTEXT_ID:
        return _build_legacy_fallback_context()
    raise NegotiationContextResolutionError(f'unsupported_negotiation_context:{requested_context_id}')


def list_official_negotiation_contexts() -> list[ResolvedNegotiationContext]:
    contexts: list[ResolvedNegotiationContext] = []
    for candidate_dir in sorted(_CONTEXTS_DIR.iterdir(), key=lambda path: path.name):
        if not candidate_dir.is_dir():
            continue
        official = _build_official_context(candidate_dir, candidate_dir / 'manifest.json')
        if official is not None:
            contexts.append(official)
    return contexts


def resolve_context_from_public_slug(public_slug: str) -> ResolvedNegotiationContext:
    normalized_slug = (public_slug or '').strip()
    for context in list_official_negotiation_contexts():
        if context.public_slug == normalized_slug:
            return context
    raise NegotiationContextResolutionError(f'unsupported_public_slug:{normalized_slug}')


def resolve_context_for_prompts_dir(prompts_dir: str | Path) -> ResolvedNegotiationContext | None:
    target = Path(prompts_dir)
    for context in list_official_negotiation_contexts():
        if context.prompts_dir == target:
            return context
    return None


def _resolve_context_dir(requested_context_id: str) -> Path | None:
    if requested_context_id == _DEFAULT_CONTEXT_ID:
        return _BASELINE_CONTEXT_DIR
    candidate_dir = _CONTEXTS_DIR / requested_context_id
    return candidate_dir if candidate_dir.exists() else None


def _build_official_context(candidate_dir: Path, manifest_path: Path) -> ResolvedNegotiationContext | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return None

    if not isinstance(manifest, dict):
        return None

    prompts_dir = candidate_dir / _string_or_default(_nested_get(manifest, 'bundle', 'prompts_dir'), 'prompts')
    assets_dir = candidate_dir / _string_or_default(_nested_get(manifest, 'bundle', 'assets_dir'), 'assets')

    required_paths = {
        'prompts_dir': prompts_dir,
        'persona_path': assets_dir / 'persona.json',
        'negotiation_brief_path': assets_dir / 'negotiation_brief.json',
        'phase_cards_path': assets_dir / 'phase_cards.json',
        'phase_classifier_card_path': assets_dir / 'phase_classifier_card.json',
    }
    if not all(path.exists() for path in required_paths.values()):
        return None

    return ResolvedNegotiationContext(
        flow_id=_string_or_default(manifest.get('flow_id'), _DEFAULT_FLOW_ID),
        context_id=_string_or_default(manifest.get('context_id'), candidate_dir.name),
        context_version=_string_or_default(manifest.get('context_version'), _DEFAULT_CONTEXT_VERSION),
        public_slug=_string_or_default(manifest.get('public_slug'), candidate_dir.name),
        context_dir=candidate_dir,
        prompts_dir=prompts_dir,
        persona_path=required_paths['persona_path'],
        negotiation_brief_path=required_paths['negotiation_brief_path'],
        phase_cards_path=required_paths['phase_cards_path'],
        phase_classifier_card_path=required_paths['phase_classifier_card_path'],
        resolution_source='official_context',
    )


def _build_legacy_fallback_context() -> ResolvedNegotiationContext:
    return ResolvedNegotiationContext(
        flow_id=_DEFAULT_FLOW_ID,
        context_id=_DEFAULT_CONTEXT_ID,
        context_version=_DEFAULT_CONTEXT_VERSION,
        public_slug=_DEFAULT_PUBLIC_SLUG,
        context_dir=_BASELINE_CONTEXT_DIR,
        prompts_dir=_LEGACY_PROMPTS_DIR,
        persona_path=_LEGACY_PROMPTS_DIR / 'persona.json',
        negotiation_brief_path=_LEGACY_PROMPTS_DIR / 'negotiation_brief.json',
        phase_cards_path=_LEGACY_PROMPTS_DIR / 'phase_cards.json',
        phase_classifier_card_path=_LEGACY_PROMPTS_DIR / 'phase_classifier_card.json',
        resolution_source='legacy_fallback',
    )


def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _string_or_default(value: object, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default
