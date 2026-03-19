"""Internal baseline context resolution for negotiation.

Phase 2 only exposes conservative helpers to resolve the official baseline
context with explicit legacy fallback. Runtime/session consumers beyond the
baseline entrypoints should not expand scope to contextual behavior yet.
"""

from .models import BoundNegotiationContext, ResolvedNegotiationContext
from .public_mapping import (
    PublicContextConflictError,
    PublicContextResolutionError,
    PublicContextSelection,
    PublicSlugResolutionError,
    resolve_public_context_selection,
    resolve_public_slug_to_context_id,
)
from .resolver import (
    NegotiationContextResolutionError,
    list_official_negotiation_contexts,
    resolve_context_for_prompts_dir,
    resolve_context_from_public_slug,
    resolve_default_negotiation_context,
    resolve_negotiation_context,
)
from .session_binding import (
    NEGOTIATION_CONTEXT_WORLD_STATE_KEY,
    bind_context_to_session,
    ensure_session_context,
    read_bound_context_from_session,
)

__all__ = [
    "BoundNegotiationContext",
    "NEGOTIATION_CONTEXT_WORLD_STATE_KEY",
    "NegotiationContextResolutionError",
    "PublicContextConflictError",
    "PublicContextResolutionError",
    "PublicContextSelection",
    "PublicSlugResolutionError",
    "ResolvedNegotiationContext",
    "bind_context_to_session",
    "ensure_session_context",
    "read_bound_context_from_session",
    "list_official_negotiation_contexts",
    "resolve_context_for_prompts_dir",
    "resolve_context_from_public_slug",
    "resolve_default_negotiation_context",
    "resolve_negotiation_context",
    "resolve_public_context_selection",
    "resolve_public_slug_to_context_id",
]
