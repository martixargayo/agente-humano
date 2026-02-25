from __future__ import annotations


def build_trace_event(trace_item: dict) -> dict:
    return dict(trace_item or {})


def list_recent_trace_events(trace_items: list[dict], limit: int = 10) -> list[dict]:
    return [dict(x) for x in (trace_items or [])][-max(0, int(limit or 0)):]
