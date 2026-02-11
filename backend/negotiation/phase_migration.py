from __future__ import annotations

from .schemas import LegacyNegotiationPhase, NegotiationPhase


_LEGACY_TO_HARVARD: dict[LegacyNegotiationPhase, tuple[NegotiationPhase, bool]] = {
    "opening": ("climate", False),
    "discovery": ("interests", False),
    "bargaining": ("adjust", False),
    "closing": ("formalize", False),
    "recovery": ("climate", True),
}

_HARVARD_PHASES: set[str] = {"climate", "interests", "options", "adjust", "formalize"}


def map_legacy_phase_to_harvard(legacy_phase: str) -> tuple[NegotiationPhase, bool]:
    candidate = str(legacy_phase or "").strip().lower()
    mapped = _LEGACY_TO_HARVARD.get(candidate)  # type: ignore[arg-type]
    if mapped:
        return mapped
    return "climate", False


def normalize_phase_candidate(phase_candidate: str, recovery_mode: bool = False) -> tuple[NegotiationPhase, str, bool, list[str]]:
    issues: list[str] = []
    raw = str(phase_candidate or "").strip().lower()
    if raw in _HARVARD_PHASES:
        return raw, raw, bool(recovery_mode), issues  # type: ignore[return-value]

    phase, mapped_recovery = map_legacy_phase_to_harvard(raw)
    if raw in _LEGACY_TO_HARVARD:
        issues.append("phase_mapped_from_legacy")
    elif raw:
        issues.append("phase_invalid")
    else:
        issues.append("phase_missing_defaulted")
    return phase, raw, bool(recovery_mode or mapped_recovery), issues
