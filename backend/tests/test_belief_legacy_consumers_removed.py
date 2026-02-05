from __future__ import annotations

from pathlib import Path

import pytest

from negotiation.validation import normalize_belief_state


LEGACY_KEYS = [
    "dynamics",
    "tom",
    "stance",
    "reasons",
    "hypotheses",
    "hypotheses_structural",
    "hypotheses_observational",
    "evaluations",
]


def _legacy_patterns() -> list[str]:
    patterns: list[str] = []
    for key in LEGACY_KEYS:
        patterns.append(f"belief_state.get('{key}')")
        patterns.append(f'belief_state.get("{key}")')
        patterns.append(f"belief_state['{key}']")
        patterns.append(f'belief_state["{key}"]')
    return patterns


def test_no_legacy_belief_state_consumers_in_negotiation() -> None:
    base = Path(__file__).resolve().parents[1] / "negotiation"
    patterns = _legacy_patterns()
    offending: list[str] = []
    for path in base.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in content:
                offending.append(f"{path}:{pattern}")
                break
    assert offending == []


def test_normalize_belief_state_warns_on_legacy_keys() -> None:
    raw = {"dynamics": {"interaction_health": "tense"}}
    with pytest.warns(DeprecationWarning, match="legacy flat keys are deprecated"):
        normalize_belief_state(raw)
