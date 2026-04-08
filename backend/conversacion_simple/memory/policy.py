from __future__ import annotations

import json
from typing import Any

from ..nodes import DialogueMessage
from ..state import ConversationSimpleCanonicalState, ConversationSimpleMemoryEpisodicItem


def trim_recent_dialogue(*, recent_dialogue: list[DialogueMessage], max_messages: int) -> tuple[list[DialogueMessage], dict[str, int]]:
    before = len(recent_dialogue)
    trimmed = list(recent_dialogue[-max_messages:]) if max_messages > 0 else []
    after = len(trimmed)
    return trimmed, {
        "memory_recent_dialogue_count_before": before,
        "memory_recent_dialogue_count_after": after,
        "memory_recent_dialogue_trimmed_count": max(0, before - after),
    }


def estimate_episodic_chars(items: list[ConversationSimpleMemoryEpisodicItem]) -> int:
    payload = [item.model_dump(mode="json") for item in items]
    return len(json.dumps(payload, ensure_ascii=False))


def should_schedule_compaction(
    *,
    canonical_state: ConversationSimpleCanonicalState,
    episodic_trigger_count: int,
    episodic_trigger_chars: int,
) -> tuple[bool, str]:
    count = len(canonical_state.memory_episodic)
    if count >= episodic_trigger_count:
        return True, "episodic_count_threshold"
    chars = estimate_episodic_chars(canonical_state.memory_episodic)
    if chars >= episodic_trigger_chars:
        return True, "episodic_chars_threshold"
    return False, "below_threshold"


def split_episodic_for_compaction(
    *,
    items: list[ConversationSimpleMemoryEpisodicItem],
    high_resolution_limit: int,
) -> tuple[list[ConversationSimpleMemoryEpisodicItem], list[ConversationSimpleMemoryEpisodicItem]]:
    if high_resolution_limit < 0:
        high_resolution_limit = 0
    if len(items) <= high_resolution_limit:
        return items, []
    pivot = len(items) - high_resolution_limit
    return items[pivot:], items[:pivot]
