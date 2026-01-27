# backend/negotiation/context_utils.py
from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

from state import Message

if TYPE_CHECKING:
    from negotiation.negotiation_graph import AgentDeps
    from state import SessionState

def _format_messages_as_text(messages: List[Message]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = msg["role"]
        label = "Vendedor" if role == "user" else "Comprador"
        lines.append(f"{label}: {msg['content']}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _user_turn_indices(history: List[Message]) -> List[int]:
    return [i for i, m in enumerate(history) if m["role"] == "user"]


def slice_last_user_turns(messages: List[Message], keep_last_n_turns: int) -> List[Message]:
    if not messages or keep_last_n_turns <= 0:
        return []
    user_starts = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_starts) <= keep_last_n_turns:
        return messages[:]
    start_idx = user_starts[-keep_last_n_turns]
    return messages[start_idx:]


def _clean_summary_text(summary: str | None) -> str:
    if not summary:
        return ""
    trimmed_summary = summary.strip()
    if not trimmed_summary or "Aún no hay resumen" in trimmed_summary:
        return ""
    return trimmed_summary


def build_memory_context(
    messages: List[Message],
    summary: str | None,
    *,
    keep_last_n_turns: int,
) -> Tuple[str, str]:
    long_memory = _clean_summary_text(summary)
    short_messages = slice_last_user_turns(messages, keep_last_n_turns)
    short_memory = _format_messages_as_text(short_messages) if short_messages else ""
    return long_memory, short_memory


def format_memory_block(long_memory: str, short_memory: str) -> str:
    sections: List[str] = []
    if long_memory.strip():
        sections.append(f"[LONG_MEMORY]\n{long_memory.strip()}")
    if short_memory.strip():
        sections.append(f"[SHORT_MEMORY]\n{short_memory.strip()}")
    if not sections:
        return "(sin memoria relevante)"
    return "\n\n".join(sections)


def should_refresh_summary(session: "SessionState", *, context_limit_turns: int) -> bool:
    turns = sum(1 for m in session.history if m.get("role") == "user")
    return turns > context_limit_turns


def maybe_refresh_summary(
    session: "SessionState",
    *,
    deps: "AgentDeps",
    context_limit_turns: int,
    keep_last_n_turns: int,
) -> dict:
    turns_before = sum(1 for m in session.history if m.get("role") == "user")
    if not should_refresh_summary(session, context_limit_turns=context_limit_turns):
        return {
            "refreshed": False,
            "turns_before": turns_before,
            "turns_after": turns_before,
            "chars_summary": len(session.summary or ""),
        }

    if not deps.summarize:
        return {
            "refreshed": False,
            "turns_before": turns_before,
            "turns_after": turns_before,
            "chars_summary": len(session.summary or ""),
        }

    suffix = slice_last_user_turns(session.history, keep_last_n_turns)
    prefix_len = len(session.history) - len(suffix)
    prefix = session.history[:prefix_len]

    new_block = _format_messages_as_text(prefix)
    existing_summary = session.summary or ""

    if deps.summarize:
        session.summary = deps.summarize(existing_summary, new_block)

    session.history = suffix
    turns_after = sum(1 for m in session.history if m.get("role") == "user")
    return {
        "refreshed": True,
        "turns_before": turns_before,
        "turns_after": turns_after,
        "chars_summary": len(session.summary or ""),
    }


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
