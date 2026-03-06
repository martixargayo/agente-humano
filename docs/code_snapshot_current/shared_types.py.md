# File Snapshot

Original path:
`backend/negociacion/shared_types.py`

Snapshot status:
`current`

Language / type:
`python`

```python
from __future__ import annotations

from enum import Enum


class ThreadMode(str, Enum):
    conversation = "conversation"
    previous_response_id = "previous_response_id"


class NodeName(str, Enum):
    memory = "memory"
    phase_classifier = "phase_classifier"
    planner = "planner"
    executor = "executor"


class NegotiationPhase(str, Enum):
    clima_humano = "clima_humano"
    descubrimiento_y_comprension = "descubrimiento_y_comprension"
    propuesta_creativa = "propuesta_creativa"
    concesiones_y_ajuste_final = "concesiones_y_ajuste_final"
    formalizacion_del_acuerdo = "formalizacion_del_acuerdo"


class SafetyPolicyAction(str, Enum):
    allow = "allow"
    clarify = "clarify"
    refuse = "refuse"
    block = "block"


class SafetyDomain(str, Enum):
    none = "none"
    medical = "medical"
    legal = "legal"
    financial = "financial"
    pii = "pii"
    dangerous_instruction = "dangerous_instruction"
    overclaim = "overclaim"


class StyleTone(str, Enum):
    neutral = "neutral"
    warm = "warm"
    firm = "firm"


class StructuredCallSource(str, Enum):
    model = "model"
    refusal = "refusal"
    fallback = "fallback"
    parse_error = "parse_error"
    exception = "exception"


class SDKCompatibilityStatus(str, Enum):
    compatible = "compatible"
    below_minimum = "below_minimum"
    unknown = "unknown"

```
