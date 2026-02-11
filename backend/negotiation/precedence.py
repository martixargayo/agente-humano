from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal[
    "recovery_guard",
    "closing_push",
    "bargaining",
    "discovery",
    "opening_or_other",
]


@dataclass(frozen=True)
class PrecedenceResult:
    mode: Mode
    reason: str
    min_policy_tags: tuple[str, ...] = ()
    block_policy_tags: tuple[str, ...] = ()
    phase_floor: str | None = None
    phase_ceiling: str | None = None
    allow_closing: bool = True


def compute_precedence(
    world: dict,
    belief: dict,
    intent: dict | None,
) -> PrecedenceResult:
    def _normalized_reason(mode: Mode, reason_key: str) -> str:
        return f"precedence:{mode} | precedence_reason:{reason_key}"

    health = (belief.get("dynamics") or {}).get("interaction_health", "stable")

    if health in {"tense", "stalled"}:
        return PrecedenceResult(
            mode="recovery_guard",
            reason=_normalized_reason("recovery_guard", f"belief:health_{health}"),
            min_policy_tags=("safe_when_tense", "deescalation"),
            block_policy_tags=("aggressive",),
            phase_floor="recovery",
            allow_closing=False,
        )

    if world.get("other_buyer_claimed") or world.get("deadline_claimed"):
        return PrecedenceResult(
            mode="discovery",
            reason=_normalized_reason("discovery", "world:credibility_signal"),
            min_policy_tags=("credibility_check",),
        )

    if world.get("price_firm") is True:
        closing_ok = bool(
            world.get("concession_made")
            or (intent and intent.get("intent_type") == "closing")
        )
        if closing_ok:
            return PrecedenceResult(
                mode="closing_push",
                reason=_normalized_reason("closing_push", "world:price_firm"),
                min_policy_tags=("closing",),
                phase_floor="closing",
                allow_closing=True,
            )
        return PrecedenceResult(
            mode="bargaining",
            reason=_normalized_reason("bargaining", "world:price_firm_without_requirements"),
            min_policy_tags=("bargaining",),
            allow_closing=False,
        )

    if world.get("price_mentioned") and world.get("concession_made"):
        return PrecedenceResult(
            mode="bargaining",
            reason=_normalized_reason("bargaining", "world:concession_made"),
            min_policy_tags=("bargaining",),
        )

    return PrecedenceResult(
        mode="opening_or_other",
        reason=_normalized_reason("opening_or_other", "history:default"),
    )
