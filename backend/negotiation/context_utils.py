# backend/negotiation/context_utils.py
from __future__ import annotations

from typing import List

from state import Message


def _format_messages_as_text(messages: List[Message]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = msg["role"]
        label = "Vendedor" if role == "user" else "Comprador"
        lines.append(f"{label}: {msg['content']}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _user_turn_indices(history: List[Message]) -> List[int]:
    return [i for i, m in enumerate(history) if m["role"] == "user"]


def build_context_snippet(
    messages: List[Message],
    summary: str | None,
    *,
    seller_only: bool = True,
    min_turns: int = 2,
    max_turns: int = 4,
    max_chars: int = 1200,
) -> str:
    if not messages:
        return "(sin mensajes previos relevantes)"

    filtered_messages = (
        [msg for msg in messages if msg.get("role") == "user"]
        if seller_only
        else list(messages)
    )
    if not filtered_messages:
        return "(sin mensajes previos relevantes)"

    user_indices = _user_turn_indices(filtered_messages)
    if not user_indices:
        snippet_text = _format_messages_as_text(filtered_messages[-max_turns:])
    else:
        turns_to_take = min(max_turns, len(user_indices))
        if turns_to_take < min_turns:
            turns_to_take = len(user_indices)
        start_idx = user_indices[-turns_to_take]
        snippet_text = _format_messages_as_text(filtered_messages[start_idx:])

    prefix = ""
    if summary:
        trimmed_summary = summary.strip()
        if trimmed_summary and "Aún no hay resumen" not in trimmed_summary:
            trimmed_summary = trimmed_summary[:240]
            prefix = f"Resumen breve: {trimmed_summary}\n"

    combined = f"{prefix}{snippet_text}".strip()
    if len(combined) > max_chars:
        combined = f"...{combined[-max_chars:]}"
    return combined
