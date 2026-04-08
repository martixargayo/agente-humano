from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FlowParitySnapshot:
    flow_id: str
    context_id: str
    bootstrap_keys: set[str]
    turn_keys: set[str]
    finalize_keys: set[str]


def common_keys(a: dict[str, Any], b: dict[str, Any]) -> set[str]:
    return set(a.keys()) & set(b.keys())


def classify_parity(*, identical: bool, equivalent: bool, deliberate_divergence: bool) -> str:
    if identical:
        return "identical"
    if equivalent:
        return "equivalent"
    if deliberate_divergence:
        return "deliberate_divergence"
    return "gap"
