from __future__ import annotations

import warnings

from .belief_compat import (
    _limit_reasons,
    has_belief_evidence_delta,
    merge_belief_buckets_update_not_rewrite,
    update_belief_state,
)


warnings.warn(
    "negotiation.belief_state_updater is deprecated; use negotiation.belief_compat or state.deps.update_belief_state_compat.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "update_belief_state",
    "merge_belief_buckets_update_not_rewrite",
    "has_belief_evidence_delta",
    "_limit_reasons",
]
