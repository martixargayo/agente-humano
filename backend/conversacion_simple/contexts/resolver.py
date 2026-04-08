from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ResolvedConversationSimpleContext

_CONTEXTS_DIR = Path(__file__).resolve().parent
_DEFAULT_FLOW_ID = "conversacion_simple"
_DEFAULT_CONTEXT_ID = "baseline"
_DEFAULT_CONTEXT_VERSION = "1.0.0"
_DEFAULT_PUBLIC_SLUG = "conversacion-simple"


class ConversationSimpleContextResolutionError(RuntimeError):
    pass


def resolve_default_conversacion_simple_context() -> ResolvedConversationSimpleContext:
    return resolve_conversacion_simple_context(context_id=_DEFAULT_CONTEXT_ID)


def resolve_conversacion_simple_context(context_id: str | None = None) -> ResolvedConversationSimpleContext:
    requested_context_id = (context_id or _DEFAULT_CONTEXT_ID).strip() or _DEFAULT_CONTEXT_ID
    candidate_dir = _CONTEXTS_DIR / requested_context_id
    if not candidate_dir.exists() or not candidate_dir.is_dir():
        raise ConversationSimpleContextResolutionError(f"unsupported_conversacion_simple_context:{requested_context_id}")

    context = _build_official_context(candidate_dir, candidate_dir / "manifest.json")
    if context is None:
        raise ConversationSimpleContextResolutionError(f"unsupported_conversacion_simple_context:{requested_context_id}")
    return context


def list_official_conversacion_simple_contexts() -> list[ResolvedConversationSimpleContext]:
    contexts: list[ResolvedConversationSimpleContext] = []
    for candidate_dir in sorted(_CONTEXTS_DIR.iterdir(), key=lambda p: p.name):
        if not candidate_dir.is_dir():
            continue
        context = _build_official_context(candidate_dir, candidate_dir / "manifest.json")
        if context is not None:
            contexts.append(context)
    return contexts


def resolve_conversacion_simple_context_from_public_slug(public_slug: str) -> ResolvedConversationSimpleContext:
    normalized = (public_slug or "").strip()
    for context in list_official_conversacion_simple_contexts():
        if context.public_slug == normalized:
            return context
    raise ConversationSimpleContextResolutionError(f"unsupported_public_slug:{normalized}")


def resolve_conversacion_simple_context_for_prompts_dir(prompts_dir: str | Path) -> ResolvedConversationSimpleContext | None:
    target = Path(prompts_dir)
    for context in list_official_conversacion_simple_contexts():
        if context.prompts_dir == target:
            return context
    return None


def _build_official_context(candidate_dir: Path, manifest_path: Path) -> ResolvedConversationSimpleContext | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(manifest, dict):
        return None

    prompts_dir = candidate_dir / _string_or_default(_nested_get(manifest, "bundle", "prompts_dir"), "prompts")
    assets_dir = candidate_dir / _string_or_default(_nested_get(manifest, "bundle", "assets_dir"), "assets")

    required_paths = {
        "prompts_dir": prompts_dir,
        "brain_prompt": prompts_dir / "brain_prompt.txt",
        "persona": assets_dir / "persona.json",
        "conversation_brief": assets_dir / "conversation_brief.json",
        "phase_cards": assets_dir / "phase_cards.json",
    }
    if not all(path.exists() for path in required_paths.values()):
        return None

    return ResolvedConversationSimpleContext(
        flow_id=_string_or_default(manifest.get("flow_id"), _DEFAULT_FLOW_ID),
        context_id=_string_or_default(manifest.get("context_id"), candidate_dir.name),
        context_version=_string_or_default(manifest.get("context_version"), _DEFAULT_CONTEXT_VERSION),
        public_slug=_string_or_default(manifest.get("public_slug"), _DEFAULT_PUBLIC_SLUG),
        context_dir=candidate_dir,
        presentation_dir=candidate_dir / "presentation",
        prompts_dir=prompts_dir,
        persona_path=required_paths["persona"],
        conversation_brief_path=required_paths["conversation_brief"],
        phase_cards_path=required_paths["phase_cards"],
        resolution_source="official_context",
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
