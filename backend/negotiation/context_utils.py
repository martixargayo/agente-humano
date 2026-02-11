# backend/negotiation/context_utils.py
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, List, Tuple, TYPE_CHECKING

from state import Message

if TYPE_CHECKING:
    from negotiation.negotiation_graph import AgentDeps
    from state import SessionState

def _is_real_user(msg: Message) -> bool:
    # Preparado para futuro: msg.get("synthetic", False)
    return msg.get("role") == "user" and not msg.get("synthetic", False)

def _format_messages_as_text(messages: List[Message]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = msg.get("role", "assistant")
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            label = "Vendedor"
        elif role == "assistant":
            label = "Comprador"
        else:
            label = str(role).upper()

        lines.append(f"{label}: {content}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _user_turn_indices(history: List[Message]) -> List[int]:
    return [i for i, m in enumerate(history) if _is_real_user(m)]


def slice_last_user_turns(messages: List[Message], keep_last_n_turns: int) -> List[Message]:
    if not messages or keep_last_n_turns <= 0:
        return []
    user_starts = [i for i, m in enumerate(messages) if _is_real_user(m)]
    if not user_starts:
        return []
    if len(user_starts) <= keep_last_n_turns:
        return messages[user_starts[0]:]
    start_idx = user_starts[-keep_last_n_turns]
    return messages[start_idx:]


def _clean_summary_text(summary: str | None) -> str:
    s = (summary or "").strip()
    if not s:
        return ""
    if _try_parse_summary_json(s) is None:
        return ""
    return s


_REQUIRED_SUMMARY_KEYS = (
    "facts",
    "open_questions",
    "constraints_limits",
    "seller_signals",
    "buyer_signals",
    "decisions",
)


def _try_parse_summary_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    for k in _REQUIRED_SUMMARY_KEYS:
        if k not in obj:
            return None
        value = obj.get(k)
        if not isinstance(value, list):
            return None
        if any(not isinstance(item, str) for item in value):
            return None
    return obj


def _canonicalize_summary_json(obj: dict) -> str:
    # Canonical JSON para estabilidad en diffs/evals/logs
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def safe_merge_summary(existing: str, candidate: str) -> str:
    existing_obj = _try_parse_summary_json(existing)
    cand_obj = _try_parse_summary_json(candidate)

    # Candidate válido → reemplazo canonical
    if cand_obj is not None:
        return _canonicalize_summary_json(cand_obj)

    # Candidate inválido → preservar existing si era válido
    if existing_obj is not None:
        return _canonicalize_summary_json(existing_obj)

    # Ambos inválidos → fallback JSON estable
    return _canonicalize_summary_json({
        "facts": [],
        "open_questions": [],
        "constraints_limits": [],
        "seller_signals": [],
        "buyer_signals": [],
        "decisions": [],
    })


def build_memory_context(
    messages: List[Message],
    summary: str | None,
    *,
    keep_last_n_turns: int,
) -> Tuple[str, str, dict]:
    long_memory = _clean_summary_text(summary)
    short_messages = slice_last_user_turns(messages, keep_last_n_turns)
    short_memory = _format_messages_as_text(short_messages) if short_messages else ""
    turns_total = sum(1 for m in messages if _is_real_user(m))
    turns_short = sum(1 for m in short_messages if _is_real_user(m))
    meta = {
        "chars_long": len(long_memory),
        "chars_short": len(short_memory),
        "turns_total": turns_total,
        "turns_short": turns_short,
    }
    return long_memory, short_memory, meta


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
    turns = sum(1 for m in session.history if _is_real_user(m))
    return turns > context_limit_turns


def maybe_refresh_summary(
    session: "SessionState",
    *,
    deps: "AgentDeps",
    context_limit_turns: int,
    keep_last_n_turns: int,
) -> dict:
    summarize_fn = getattr(deps, "summarize", None)

    turns_before = sum(1 for m in session.history if _is_real_user(m))
    chars_before = len(session.summary or "")

    if not should_refresh_summary(session, context_limit_turns=context_limit_turns):
        return {
            "refreshed": False,
            "turns_before": turns_before,
            "turns_after": turns_before,
            "prefix_messages": 0,
            "suffix_messages": len(session.history),
            "chars_summary_before": chars_before,
            "chars_summary_after": chars_before,
            "prefix_hash": "",
            "reason": "below_limit",
        }

    if not callable(summarize_fn):
        return {
            "refreshed": False,
            "turns_before": turns_before,
            "turns_after": turns_before,
            "prefix_messages": 0,
            "suffix_messages": len(session.history),
            "chars_summary_before": chars_before,
            "chars_summary_after": chars_before,
            "prefix_hash": "",
            "reason": "no_summarizer",
        }

    suffix = slice_last_user_turns(session.history, keep_last_n_turns)
    prefix_len = len(session.history) - len(suffix)
    prefix = session.history[:prefix_len]

    new_block = _format_messages_as_text(prefix)
    existing_summary = session.summary or ""

    # hash corto para audit/debug (correlación en logs)
    prefix_hash = hashlib.sha256(new_block.encode("utf-8")).hexdigest()[:10]

    raw_candidate = summarize_fn(existing_summary, new_block)
    candidate_obj = _try_parse_summary_json(raw_candidate)
    existing_obj = _try_parse_summary_json(existing_summary)
    candidate_invalid = candidate_obj is None and bool((raw_candidate or "").strip())
    merge_used_existing = candidate_invalid and existing_obj is not None

    session.summary = safe_merge_summary(existing_summary, raw_candidate)

    # recorta el historial a la ventana de turns vivos
    session.history = suffix

    turns_after = sum(1 for m in session.history if _is_real_user(m))
    chars_after = len(session.summary or "")

    return {
        "refreshed": True,
        "turns_before": turns_before,
        "turns_after": turns_after,
        "prefix_messages": len(prefix),
        "suffix_messages": len(suffix),
        "chars_summary_before": chars_before,
        "chars_summary_after": chars_after,
        "prefix_hash": prefix_hash,
        "candidate_invalid": candidate_invalid,
        "merge_used_existing": merge_used_existing,
        "reason": "summarized",
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
        [msg for msg in messages if _is_real_user(msg)]
        if seller_only
        else [msg for msg in messages if (msg.get("content") or "").strip()]
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
    trimmed_summary = _clean_summary_text(summary)
    if trimmed_summary:
        summary_obj = _try_parse_summary_json(trimmed_summary)
        if summary_obj:
            parts = []
            for key in _REQUIRED_SUMMARY_KEYS:
                items = summary_obj.get(key) or []
                if items:
                    snippet_items = "; ".join(items[:2])
                    parts.append(f"{key}: {snippet_items}")
            if parts:
                prefix = f"Resumen breve: {' | '.join(parts)[:240]}\n"

    combined = f"{prefix}{snippet_text}".strip()
    if len(combined) > max_chars:
        combined = f"...{combined[-max_chars:]}"
    return combined
