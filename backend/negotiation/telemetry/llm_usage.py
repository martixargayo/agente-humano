from __future__ import annotations

from typing import Any


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def extract_llm_usage(raw: Any) -> dict[str, Any]:
    """Best-effort extraction of model/token usage from provider responses."""
    response_metadata = getattr(raw, "response_metadata", None)
    usage_metadata = getattr(raw, "usage_metadata", None)
    if not isinstance(response_metadata, dict):
        response_metadata = {}
    if not isinstance(usage_metadata, dict):
        usage_metadata = {}

    model = (
        response_metadata.get("model_name")
        or response_metadata.get("model")
        or usage_metadata.get("model_name")
        or usage_metadata.get("model")
    )

    token_usage = response_metadata.get("token_usage")
    if not isinstance(token_usage, dict):
        token_usage = {}

    tokens_in = (
        usage_metadata.get("input_tokens")
        or usage_metadata.get("prompt_tokens")
        or token_usage.get("prompt_tokens")
        or token_usage.get("input_tokens")
    )
    tokens_out = (
        usage_metadata.get("output_tokens")
        or usage_metadata.get("completion_tokens")
        or token_usage.get("completion_tokens")
        or token_usage.get("output_tokens")
    )

    queue_ms = response_metadata.get("queue_ms") or response_metadata.get("queue_time_ms")
    ttfb_ms = response_metadata.get("ttfb_ms") or response_metadata.get("first_token_ms")

    return {
        "model": str(model) if model else None,
        "tokens_in": _as_int(tokens_in),
        "tokens_out": _as_int(tokens_out),
        "queue_ms": _as_int(queue_ms),
        "ttfb_ms": _as_int(ttfb_ms),
    }
