from __future__ import annotations

import json
from pathlib import Path

from .models import ResolvedCommunicationContext

_CONTEXTS_DIR = Path(__file__).resolve().parent
_DEFAULT_FLOW_ID = 'comunicacion'
_DEFAULT_CONTEXT_ID = 'baseline_current'
_DEFAULT_CONTEXT_VERSION = '1.0.0'
_DEFAULT_PUBLIC_SLUG = 'comunicacion'


class CommunicationContextResolutionError(RuntimeError):
    pass


def resolve_default_communication_context() -> ResolvedCommunicationContext:
    return resolve_communication_context(_DEFAULT_CONTEXT_ID)


def resolve_communication_context(context_id: str | None = None) -> ResolvedCommunicationContext:
    requested_context_id = (context_id or _DEFAULT_CONTEXT_ID).strip() or _DEFAULT_CONTEXT_ID
    candidate_dir = _CONTEXTS_DIR / requested_context_id
    if not candidate_dir.exists() or not candidate_dir.is_dir():
        raise CommunicationContextResolutionError(f'unsupported_communication_context:{requested_context_id}')

    manifest_path = candidate_dir / 'manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise CommunicationContextResolutionError(f'invalid_communication_manifest:{requested_context_id}') from exc

    if not isinstance(manifest, dict):
        raise CommunicationContextResolutionError(f'invalid_communication_manifest:{requested_context_id}')

    presentation_dir = candidate_dir / 'presentation'
    assets_dir = candidate_dir / 'assets'
    required_paths = [
        presentation_dir / 'presentation_config.json',
        assets_dir / 'activity_brief.json',
        assets_dir / 'capture_policy.json',
    ]
    if not all(path.exists() and path.is_file() for path in required_paths):
        raise CommunicationContextResolutionError(f'incomplete_communication_context:{requested_context_id}')

    return ResolvedCommunicationContext(
        flow_id=_string_or_default(manifest.get('flow_id'), _DEFAULT_FLOW_ID),
        context_id=_string_or_default(manifest.get('context_id'), candidate_dir.name),
        context_version=_string_or_default(manifest.get('context_version'), _DEFAULT_CONTEXT_VERSION),
        public_slug=_string_or_default(manifest.get('public_slug'), _DEFAULT_PUBLIC_SLUG),
        context_dir=candidate_dir,
        presentation_dir=presentation_dir,
        assets_dir=assets_dir,
        manifest_path=manifest_path,
        resolution_source='official_context',
    )


def list_official_communication_contexts() -> list[ResolvedCommunicationContext]:
    contexts: list[ResolvedCommunicationContext] = []
    for candidate_dir in sorted(_CONTEXTS_DIR.iterdir(), key=lambda path: path.name):
        if not candidate_dir.is_dir():
            continue
        try:
            contexts.append(resolve_communication_context(candidate_dir.name))
        except CommunicationContextResolutionError:
            continue
    return contexts


def resolve_context_from_public_slug(public_slug: str) -> ResolvedCommunicationContext:
    normalized_slug = (public_slug or '').strip()
    for context in list_official_communication_contexts():
        if context.public_slug == normalized_slug:
            return context
    raise CommunicationContextResolutionError(f'unsupported_public_slug:{normalized_slug}')


def _string_or_default(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
