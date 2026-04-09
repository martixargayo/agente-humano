from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.forensics_structured_outputs_wire_capture import build_report


def test_brain_provider_request_equals_serialized_http_body() -> None:
    report = build_report()
    brain = report["brain"]
    assert brain["provider_request_equals_http_body"] is True
    assert brain["schema_equals_normalized"] is True
    assert brain["root_required_has_memory_episodic_append"] is False
    assert brain["brainstatepatch_required_has_memory_episodic_append"] is True


def test_summarizer_provider_request_equals_serialized_http_body() -> None:
    report = build_report()
    summarizer = report["summarizer"]
    assert summarizer["provider_request_equals_http_body"] is True
    assert summarizer["schema_equals_normalized"] is True


def test_raw_http_equivalence_matches_sdk_request_payload() -> None:
    report = build_report()
    raw = report["raw_http_equivalence"]
    assert raw["equal"] is True
    assert raw["request_hash"] == raw["serialized_hash"]


def test_local_validator_gap_root_anyof_still_marked_valid_locally() -> None:
    report = build_report()
    gap = report["local_validator_gaps"]
    assert gap["local_validation"]["valid"] is True
