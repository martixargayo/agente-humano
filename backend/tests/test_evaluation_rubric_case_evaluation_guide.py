"""Tests for the case_evaluation_guide field in NegotiationDomainRubricV1.

Covers:
- conversacion-dificil-periodista rubric loads without ValidationError
- case_evaluation_guide is preserved after validation
- Rubrics without case_evaluation_guide continue to load correctly
- Truly unknown root fields still raise ValidationError (strict mode maintained)
- RubricLoader round-trip for the periodista context
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluacion.contracts.models import (  # noqa: E402
    CaseEvaluationGuide,
    DomainContext,
    FeedbackInputBundleV1,
    NegotiationDomainRubricV1,
)
from evaluacion.domains.conversacion_simple.rubric_loader import (  # noqa: E402
    _load_rubric_from_path,
    load_conversacion_simple_rubric_v1,
)
from evaluacion.engine.input_shaping import shape_core_input  # noqa: E402

PERIODISTA_RUBRIC_PATH = (
    ROOT
    / "conversacion_simple"
    / "contexts"
    / "conversacion-dificil-periodista"
    / "evaluation"
    / "rubric.json"
)
BASELINE_RUBRIC_PATH = (
    ROOT / "conversacion_simple" / "contexts" / "baseline" / "evaluation" / "rubric.json"
)


def test_periodista_rubric_loads_without_validation_error() -> None:
    """The rubric file must validate cleanly against NegotiationDomainRubricV1."""
    _load_rubric_from_path.cache_clear()
    rubric = _load_rubric_from_path(str(PERIODISTA_RUBRIC_PATH))
    assert isinstance(rubric, NegotiationDomainRubricV1)


def test_periodista_rubric_case_evaluation_guide_is_preserved() -> None:
    """case_evaluation_guide must survive round-trip through model_validate."""
    _load_rubric_from_path.cache_clear()
    rubric = _load_rubric_from_path(str(PERIODISTA_RUBRIC_PATH))

    assert rubric.case_evaluation_guide is not None
    assert isinstance(rubric.case_evaluation_guide, CaseEvaluationGuide)
    assert rubric.case_evaluation_guide.case_id == "carmen_redaccion_periodico"
    assert len(rubric.case_evaluation_guide.visible_behaviors) > 0
    assert len(rubric.case_evaluation_guide.likely_background_hypotheses) > 0

    cbm = rubric.case_evaluation_guide.cognitive_behavioral_model
    assert len(cbm.possible_thoughts) > 0
    assert len(cbm.possible_emotions) > 0
    assert len(cbm.possible_behaviors) > 0


def test_periodista_rubric_case_evaluation_guide_survives_model_dump() -> None:
    """case_evaluation_guide must be present in model_dump so the LLM receives it."""
    _load_rubric_from_path.cache_clear()
    rubric = _load_rubric_from_path(str(PERIODISTA_RUBRIC_PATH))

    dumped = rubric.model_dump(mode="json")
    assert "case_evaluation_guide" in dumped
    assert dumped["case_evaluation_guide"] is not None
    assert dumped["case_evaluation_guide"]["case_id"] == "carmen_redaccion_periodico"


def test_baseline_rubric_loads_without_case_evaluation_guide() -> None:
    """Rubrics that don't have case_evaluation_guide must continue to load fine."""
    _load_rubric_from_path.cache_clear()
    rubric = _load_rubric_from_path(str(BASELINE_RUBRIC_PATH))

    assert isinstance(rubric, NegotiationDomainRubricV1)
    assert rubric.case_evaluation_guide is None


def test_truly_unknown_root_field_still_raises() -> None:
    """extra='forbid' must remain active: a random unknown field must fail."""
    payload = json.loads(PERIODISTA_RUBRIC_PATH.read_text(encoding="utf-8"))
    payload["unknown_field_xyz"] = "should_be_rejected"

    with pytest.raises(ValidationError) as exc_info:
        NegotiationDomainRubricV1.model_validate(payload)

    errors = exc_info.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errors)


def test_rubric_loader_loads_periodista_context_via_domain_context() -> None:
    """load_conversacion_simple_rubric_v1 must work end-to-end for this context."""
    _load_rubric_from_path.cache_clear()
    domain_ctx = DomainContext(
        domain="conversacion_simple",
        flow_id="conversacion_simple",
        context_id="conversacion-dificil-periodista",
    )

    rubric = load_conversacion_simple_rubric_v1(domain_ctx)
    assert isinstance(rubric, NegotiationDomainRubricV1)
    assert rubric.case_evaluation_guide is not None
    assert rubric.metadata.case_title == "Conversación difícil con Carmen"


def test_periodista_rubric_roundtrip_validate_dump_validate_keeps_case_guide() -> None:
    """Round-trip by JSON dump must keep case_evaluation_guide parseable."""
    payload = json.loads(PERIODISTA_RUBRIC_PATH.read_text(encoding="utf-8"))
    rubric = NegotiationDomainRubricV1.model_validate(payload)
    reloaded = NegotiationDomainRubricV1.model_validate(rubric.model_dump(mode="json"))

    assert reloaded.case_evaluation_guide is not None
    assert reloaded.case_evaluation_guide.case_id == "carmen_redaccion_periodico"


def test_shape_core_input_accepts_periodista_context_without_validation_error() -> None:
    """Pipeline shaping must succeed (regression for original runtime failure cause)."""
    bundle = FeedbackInputBundleV1.model_validate(
        {
            "schema_version": "feedback_input_bundle.v1",
            "evaluation_id": "eval-case-guide",
            "session_ref": {"user_id": "u", "session_id": "s"},
            "conversation": {
                "turns": [
                    {
                        "turn_index": 1,
                        "turn_id": "t1",
                        "user_text": "Hola Carmen",
                        "assistant_text": "Gracias por compartirlo.",
                    }
                ]
            },
            "conversation_stats": {
                "turn_count": 1,
                "duration_seconds": 10,
                "user_avg_chars": 11,
                "assistant_avg_chars": 27,
            },
            "domain_context": {
                "domain": "conversacion_simple",
                "flow_id": "conversacion_simple",
                "context_id": "conversacion-dificil-periodista",
            },
            "derived_facts": {
                "question_turn_indexes": [1],
                "close_signals_count": 0,
                "offer_signals_count": 0,
                "blocker_signals_count": 0,
            },
            "trace_digest": {"trace_count": 0, "guardrail_events_count": 0},
        }
    )

    core_input = shape_core_input(bundle)
    assert core_input.domain_rubric.case_evaluation_guide is not None
    assert core_input.domain_rubric.case_evaluation_guide.case_id == "carmen_redaccion_periodico"
