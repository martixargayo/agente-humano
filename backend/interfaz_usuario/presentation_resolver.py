from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from negociacion.contexts.resolver import NegotiationContextResolutionError, resolve_negotiation_context
from conversacion_simple.contexts import ConversationSimpleContextResolutionError, resolve_conversacion_simple_context

from .presentation_models import PresentationConfig

_DEFAULTS_PATH = Path(__file__).resolve().parent / 'presentation_defaults.json'


class PresentationConfigResolutionError(RuntimeError):
    pass


def resolve_presentation_config_for_context(context_id: str | None) -> PresentationConfig:
    try:
        context = resolve_negotiation_context(context_id)
    except NegotiationContextResolutionError:
        try:
            context = resolve_conversacion_simple_context(context_id)
        except ConversationSimpleContextResolutionError as exc:
            raise PresentationConfigResolutionError(f"presentation_unknown_context:{context_id}") from exc
    defaults = _load_json_object(_DEFAULTS_PATH)
    overrides_path = context.presentation_dir / 'presentation_config.json'
    overrides = _load_json_object(overrides_path) if overrides_path.exists() else {}
    merged = _deep_merge(defaults, overrides)
    normalized = _normalize_asset_urls(merged, context_id=context.context_id)
    return PresentationConfig.model_validate(normalized)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:  # config load error should be explicit
        raise PresentationConfigResolutionError(f'presentation_config_load_failed:{path}') from exc
    if not isinstance(payload, dict):
        raise PresentationConfigResolutionError(f'presentation_config_not_object:{path}')
    return payload


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _normalize_asset_urls(payload: dict[str, Any], *, context_id: str) -> dict[str, Any]:
    normalized = deepcopy(payload)
    avatar_model = normalized.get('avatar', {}).get('model', {}) if isinstance(normalized.get('avatar'), dict) else {}
    model_url = avatar_model.get('url')
    if isinstance(model_url, str) and model_url.strip():
        avatar_model['url'] = _normalize_asset_url(model_url.strip(), context_id=context_id)

    background = normalized.get('background')
    if isinstance(background, dict):
        bg_url = background.get('url')
        if isinstance(bg_url, str) and bg_url.strip():
            background['url'] = _normalize_asset_url(bg_url.strip(), context_id=context_id)
    return normalized


def _normalize_asset_url(value: str, *, context_id: str) -> str:
    if value.startswith('/') or '://' in value or value.startswith('data:'):
        return value
    relative = value.lstrip('./').lstrip('/')
    return f'/interfaz_usuario/context-assets/{context_id}/{relative}'
