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


def split_dialogue_into_turns(*, recent_dialogue: list[DialogueMessage]) -> list[list[DialogueMessage]]:
    turns: list[list[DialogueMessage]] = []
    current_turn: list[DialogueMessage] = []
    for message in recent_dialogue:
        if message.role == "user":
            if current_turn:
                turns.append(current_turn)
            current_turn = [message]
            continue
        if not current_turn:
            current_turn = [message]
        else:
            current_turn.append(message)
    if current_turn:
        turns.append(current_turn)
    return turns


def flatten_turns(*, turns: list[list[DialogueMessage]]) -> list[DialogueMessage]:
    return [message for turn in turns for message in turn]


def trim_recent_dialogue_by_turns(
    *,
    recent_dialogue: list[DialogueMessage],
    context_limit_turns: int,
    keep_last_n_turns: int,
) -> tuple[list[DialogueMessage], list[list[DialogueMessage]], dict[str, int]]:
    turns = split_dialogue_into_turns(recent_dialogue=recent_dialogue)
    turn_count_before = len(turns)
    keep_turns = max(0, keep_last_n_turns)
    limit_turns = max(0, context_limit_turns)
    archived_turns: list[list[DialogueMessage]] = []
    if turn_count_before > limit_turns:
        if keep_turns == 0:
            archived_turns = turns
            turns_after = []
        else:
            archived_turns = turns[:-keep_turns]
            turns_after = turns[-keep_turns:]
    else:
        turns_after = turns
    kept_messages = flatten_turns(turns=turns_after)
    archived_messages = flatten_turns(turns=archived_turns)
    return kept_messages, archived_turns, {
        "memory_recent_dialogue_count_before": len(recent_dialogue),
        "memory_recent_dialogue_count_after": len(kept_messages),
        "memory_recent_dialogue_trimmed_count": max(0, len(recent_dialogue) - len(kept_messages)),
        "memory_recent_turn_count_before": turn_count_before,
        "memory_recent_turn_count_after": len(turns_after),
        "memory_recent_turns_archived_count": len(archived_turns),
        "memory_recent_messages_archived_count": len(archived_messages),
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
