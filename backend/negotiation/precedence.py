from __future__ import annotations

from dataclasses import dataclass

from .elementos.strategy_definitions import (
    MODE_BARGAINING,
    MODE_CLOSING_PUSH,
    MODE_DISCOVERY,
    MODE_OPENING_OR_OTHER,
    MODE_RECOVERY_GUARD,
    Mode,
    PHASE_CLOSING,
    PHASE_RECOVERY,
    PRECEDENCE_BARGAINING_MIN_TAGS,
    PRECEDENCE_CLOSING_PUSH_MIN_TAGS,
    PRECEDENCE_DISCOVERY_MIN_TAGS,
    PRECEDENCE_RECOVERY_BLOCK_TAGS,
    PRECEDENCE_RECOVERY_MIN_TAGS,
)


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
            mode=MODE_RECOVERY_GUARD,
            reason=_normalized_reason(MODE_RECOVERY_GUARD, f"belief:health_{health}"),
            min_policy_tags=PRECEDENCE_RECOVERY_MIN_TAGS,
            block_policy_tags=PRECEDENCE_RECOVERY_BLOCK_TAGS,
            phase_floor=PHASE_RECOVERY,
            allow_closing=False,
        )

    if world.get("other_buyer_claimed") or world.get("deadline_claimed"):
        return PrecedenceResult(
            mode=MODE_DISCOVERY,
            reason=_normalized_reason(MODE_DISCOVERY, "world:credibility_signal"),
            min_policy_tags=PRECEDENCE_DISCOVERY_MIN_TAGS,
        )

    if world.get("price_firm") is True:
        closing_ok = bool(
            world.get("concession_made")
            or (intent and intent.get("intent_type") == "closing")
        )
        if closing_ok:
            return PrecedenceResult(
                mode=MODE_CLOSING_PUSH,
                reason=_normalized_reason(MODE_CLOSING_PUSH, "world:price_firm"),
                min_policy_tags=PRECEDENCE_CLOSING_PUSH_MIN_TAGS,
                phase_floor=PHASE_CLOSING,
                allow_closing=True,
            )
        return PrecedenceResult(
            mode=MODE_BARGAINING,
            reason=_normalized_reason(MODE_BARGAINING, "world:price_firm_without_requirements"),
            min_policy_tags=PRECEDENCE_BARGAINING_MIN_TAGS,
            allow_closing=False,
        )

    if world.get("price_mentioned") and world.get("concession_made"):
        return PrecedenceResult(
            mode=MODE_BARGAINING,
            reason=_normalized_reason(MODE_BARGAINING, "world:concession_made"),
            min_policy_tags=PRECEDENCE_BARGAINING_MIN_TAGS,
        )

    return PrecedenceResult(
        mode=MODE_OPENING_OR_OTHER,
        reason=_normalized_reason(MODE_OPENING_OR_OTHER, "history:default"),
    )
