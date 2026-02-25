from __future__ import annotations

from typing import Any


def _as_dict(data: Any) -> dict:
    return data if isinstance(data, dict) else {}


def normalize_world_buckets(raw: object, default_turn: int | None = None, **kwargs: Any) -> dict:
    _ = default_turn
    _ = kwargs
    data = _as_dict(raw)
    return {
        "interaction": _as_dict(data.get("interaction")),
        "notes": _as_dict(data.get("notes")),
    }


def normalize_belief_buckets(raw: object) -> dict:
    data = _as_dict(raw)
    return {
        "signals": _as_dict(data.get("signals")),
        "flags": _as_dict(data.get("flags")),
    }


def normalize_phase_state(raw: object) -> dict:
    data = _as_dict(raw)
    phase = str(data.get("phase", "clima_humano") or "clima_humano")
    return {
        "phase": phase,
        "phase_effective": str(data.get("phase_effective", phase) or phase),
        "confidence": float(data.get("confidence", 0.7) or 0.7),
        "reasons": list(data.get("reasons", [])) if isinstance(data.get("reasons"), list) else [],
    }
