from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from evaluacion.contracts.models import DomainContext, NegotiationDomainRubricV1

from .assets_loader import resolve_negotiation_evaluation_assets


@lru_cache(maxsize=8)
def _load_rubric_from_path(path: str) -> NegotiationDomainRubricV1:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    return NegotiationDomainRubricV1.model_validate(payload)


def load_negotiation_rubric_v1(domain_context: DomainContext | None = None) -> NegotiationDomainRubricV1:
    assets = resolve_negotiation_evaluation_assets(domain_context)
    return _load_rubric_from_path(str(assets.rubric_path))
