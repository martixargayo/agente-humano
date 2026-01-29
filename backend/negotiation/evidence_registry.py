from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EvidencePathSpec:
    path: str
    value_kind: str
    unit: str | None = None
    qualifiers_allowed: set[str] = frozenset()
    bucketize: Callable[[Any], Any] = lambda v: v
    coerce: Callable[[Any], Any] = lambda v: v


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "sí", "si"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return bool(value)


def _bucket_bool(value: Any) -> str:
    return "1" if _coerce_bool(value) else "0"


def _bucket_string(value: Any, limit: int = 40) -> str:
    return str(value or "")[:limit].strip().lower()


EVIDENCE_PATH_REGISTRY: dict[str, EvidencePathSpec] = {
    "negotiation.price.offer": EvidencePathSpec(
        path="negotiation.price.offer",
        value_kind="number",
        unit="EUR",
        qualifiers_allowed=frozenset({"speaker"}),
        bucketize=lambda v: round(float(v) / 10.0) * 10.0,
        coerce=lambda v: float(v),
    ),
    "negotiation.price.mentioned": EvidencePathSpec(
        path="negotiation.price.mentioned",
        value_kind="bool",
        qualifiers_allowed=frozenset({"speaker", "has_number"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.price.firmness": EvidencePathSpec(
        path="negotiation.price.firmness",
        value_kind="enum",
        qualifiers_allowed=frozenset({"strength"}),
        bucketize=lambda v: str(v),
        coerce=lambda v: str(v),
    ),
    "negotiation.deadline.days": EvidencePathSpec(
        path="negotiation.deadline.days",
        value_kind="number",
        unit="days",
        qualifiers_allowed=frozenset({"kind"}),
        bucketize=lambda v: int(float(v)),
        coerce=lambda v: int(float(v)),
    ),
    "negotiation.deadline.claimed": EvidencePathSpec(
        path="negotiation.deadline.claimed",
        value_kind="bool",
        qualifiers_allowed=frozenset({"kind"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.urgency.claimed": EvidencePathSpec(
        path="negotiation.urgency.claimed",
        value_kind="bool",
        qualifiers_allowed=frozenset({"reason"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.other_buyer.claimed": EvidencePathSpec(
        path="negotiation.other_buyer.claimed",
        value_kind="bool",
        qualifiers_allowed=frozenset({"offer_price", "timing"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.concession.made": EvidencePathSpec(
        path="negotiation.concession.made",
        value_kind="bool",
        qualifiers_allowed=frozenset({"detail"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.batna.claimed": EvidencePathSpec(
        path="negotiation.batna.claimed",
        value_kind="bool",
        qualifiers_allowed=frozenset({"detail"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
    "negotiation.tone.signal": EvidencePathSpec(
        path="negotiation.tone.signal",
        value_kind="enum",
        qualifiers_allowed=frozenset({"marker"}),
        bucketize=lambda v: str(v),
        coerce=lambda v: str(v),
    ),
    "negotiation.evidence.offered": EvidencePathSpec(
        path="negotiation.evidence.offered",
        value_kind="bool",
        qualifiers_allowed=frozenset({"detail"}),
        bucketize=_bucket_bool,
        coerce=_coerce_bool,
    ),
}


def get_spec(path: str) -> EvidencePathSpec | None:
    return EVIDENCE_PATH_REGISTRY.get(path)
