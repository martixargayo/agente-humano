"""Internal baseline context resolution for negotiation.

Phase 2 only exposes conservative helpers to resolve the official baseline
context with explicit legacy fallback. Runtime/session consumers beyond the
baseline entrypoints should not expand scope to contextual behavior yet.
"""

from .models import ResolvedNegotiationContext
from .resolver import NegotiationContextResolutionError, resolve_default_negotiation_context, resolve_negotiation_context

__all__ = [
    "NegotiationContextResolutionError",
    "ResolvedNegotiationContext",
    "resolve_default_negotiation_context",
    "resolve_negotiation_context",
]
