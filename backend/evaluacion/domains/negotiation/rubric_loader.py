from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from evaluacion.contracts.models import NegotiationDomainRubricV1

_RUBRIC_PATH = Path(__file__).resolve().parent / "rubrics" / "negotiation_rubric_v1.json"


@lru_cache(maxsize=1)
def load_negotiation_rubric_v1() -> NegotiationDomainRubricV1:
    payload = json.loads(_RUBRIC_PATH.read_text(encoding="utf-8"))
    return NegotiationDomainRubricV1.model_validate(payload)
