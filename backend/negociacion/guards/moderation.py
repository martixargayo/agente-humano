from __future__ import annotations

import logging

import openai

from .constants import HIGH_RISK_MODERATION_CATEGORIES
from .models import ModerationSignals

logger = logging.getLogger(__name__)

MODERATION_MODEL = "omni-moderation-latest"


def run_moderation_check(*, client: openai.OpenAI | None, text: str, enabled: bool) -> ModerationSignals:
    if not enabled:
        return ModerationSignals(used=False, unavailable_reason="disabled")
    if client is None:
        return ModerationSignals(used=False, unavailable_reason="client_unavailable")
    if not text.strip():
        return ModerationSignals(used=False, unavailable_reason="empty_text")

    try:
        response = client.moderations.create(model=MODERATION_MODEL, input=text)
        results = getattr(response, "results", None) or []
        if not results:
            return ModerationSignals(used=True, flagged_categories=[])
        first = results[0]
        categories = getattr(first, "categories", None)
        payload = categories.model_dump() if hasattr(categories, "model_dump") else dict(categories or {})
        flagged = [name for name, value in payload.items() if bool(value)]
        return ModerationSignals(used=True, flagged_categories=sorted(set(flagged)))
    except Exception as exc:
        logger.warning("moderation_check_failed error=%s", exc)
        return ModerationSignals(used=False, unavailable_reason=f"moderation_exception:{exc.__class__.__name__}")


def has_high_risk_moderation_flags(flags: list[str]) -> bool:
    return any(flag in HIGH_RISK_MODERATION_CATEGORIES for flag in flags)
