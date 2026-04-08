from __future__ import annotations

from ..state import ConversationSimpleMemoryEpisodicItem


def build_deterministic_fallback_summary(*, items: list[ConversationSimpleMemoryEpisodicItem], max_chars: int) -> str:
    if not items:
        return ""
    oldest = items[: max(1, len(items) // 2)]
    text = " | ".join(f"{item.event_type}:{item.event_summary}" for item in oldest)
    return text[:max_chars]
