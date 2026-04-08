from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .resolver import (
    ConversationSimpleContextResolutionError,
    resolve_conversacion_simple_context,
    resolve_conversacion_simple_context_from_public_slug,
    resolve_default_conversacion_simple_context,
)


class ConversationSimplePublicSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_id: str
    public_slug: str


class ConversationSimplePublicResolutionError(RuntimeError):
    pass


class ConversationSimplePublicConflictError(ConversationSimplePublicResolutionError):
    pass


class ConversationSimplePublicSlugResolutionError(ConversationSimplePublicResolutionError):
    pass


def resolve_conversacion_simple_public_slug_to_context_id(public_slug: str | None) -> str:
    default_context = resolve_default_conversacion_simple_context()
    normalized_slug = (public_slug or "").strip()
    if not normalized_slug:
        return default_context.context_id
    try:
        return resolve_conversacion_simple_context_from_public_slug(normalized_slug).context_id
    except ConversationSimpleContextResolutionError as exc:
        raise ConversationSimplePublicSlugResolutionError(f"unsupported_public_slug:{normalized_slug}") from exc


def resolve_conversacion_simple_public_context_selection(*, context_id: str | None = None, public_slug: str | None = None) -> ConversationSimplePublicSelection:
    normalized_context_id = (context_id or "").strip() or None
    normalized_public_slug = (public_slug or "").strip() or None

    if normalized_context_id is None and normalized_public_slug is None:
        default_context = resolve_default_conversacion_simple_context()
        return ConversationSimplePublicSelection(context_id=default_context.context_id, public_slug=default_context.public_slug)

    if normalized_context_id is None:
        resolved_context_id = resolve_conversacion_simple_public_slug_to_context_id(normalized_public_slug)
        resolved_context = resolve_conversacion_simple_context(resolved_context_id)
        return ConversationSimplePublicSelection(context_id=resolved_context.context_id, public_slug=resolved_context.public_slug)

    if normalized_public_slug is not None:
        resolved_from_slug = resolve_conversacion_simple_public_slug_to_context_id(normalized_public_slug)
        if resolved_from_slug != normalized_context_id:
            raise ConversationSimplePublicConflictError(
                f"context_input_conflict:context_id={normalized_context_id}:public_slug={normalized_public_slug}"
            )

    resolved_context = resolve_conversacion_simple_context(normalized_context_id)
    return ConversationSimplePublicSelection(context_id=resolved_context.context_id, public_slug=resolved_context.public_slug)
