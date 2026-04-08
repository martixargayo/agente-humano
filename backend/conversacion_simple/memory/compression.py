from __future__ import annotations

from ..state import ConversationSimpleMemoryEpisodicItem


def build_compacted_summary(
    *,
    previous_summary: str,
    candidates: list[ConversationSimpleMemoryEpisodicItem],
    max_chars: int,
) -> str:
    bullet_lines = [f"- [{item.event_type}] {item.event_summary}" for item in candidates]
    prefix = previous_summary.strip()
    combined = "\n".join([part for part in [prefix, *bullet_lines] if part]).strip()
    if len(combined) <= max_chars:
        return combined
    # deterministic tail-preserving truncation
    return combined[-max_chars:]
