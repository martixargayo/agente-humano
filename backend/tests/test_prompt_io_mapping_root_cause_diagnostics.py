from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import resolve_negotiation_context
from negociacion.contexts.prompt_io_mapping import PromptIOMappingError, load_prompt_io_adapter
from scripts.forensics_prompt_io_mapping_causality import build_report


REPORT = build_report()


def _scenario(report: dict[str, object], scenario_id: str) -> dict[str, object]:
    for item in report["scenarios"]:  # type: ignore[index]
        if item.get("scenario_id") == scenario_id:
            return item
    raise AssertionError(f"scenario_not_found:{scenario_id}")


def test_context_specific_mapping_resolution() -> None:
    baseline = resolve_negotiation_context("baseline_current")
    validacion = resolve_negotiation_context("validacion_multicontexto")
    sala = resolve_negotiation_context("sala_reuniones")

    assert baseline.prompt_io_mapping_path is None
    assert validacion.prompt_io_mapping_path is None
    assert sala.prompt_io_mapping_path is not None
    assert sala.prompt_io_mapping_path.name == "prompt_io_mapping.json"


def test_load_prompt_io_adapter_no_cross_context_reuse_identity() -> None:
    rows = REPORT["adapter_audit"]["rows"]  # type: ignore[index]
    by_context = {row["context_id"]: row for row in rows}

    sala_row = by_context["sala_reuniones"]
    baseline_row = by_context["baseline_current"]

    assert sala_row["unique_adapter_instances"] == 3
    assert baseline_row["unique_adapter_instances"] == 3
    assert sala_row["versions"] == ["v2", "v2", "v2"]
    assert baseline_row["versions"] == ["v1", "v1", "v1"]


def test_adapter_config_not_mutated_by_runtime_usage() -> None:
    audit = REPORT["mapping_mutation_audit"]  # type: ignore[index]
    assert audit["mutated"] is False
    assert audit["config_hash_before"] == audit["config_hash_after"]


def test_order_of_loading_does_not_change_mapping_hash() -> None:
    sala = resolve_negotiation_context("sala_reuniones")
    first = load_prompt_io_adapter(sala.prompt_io_mapping_path)
    _ = load_prompt_io_adapter(resolve_negotiation_context("baseline_current").prompt_io_mapping_path)
    second = load_prompt_io_adapter(sala.prompt_io_mapping_path)

    first_dump = json.dumps(first.config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    second_dump = json.dumps(second.config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    assert first_dump == second_dump


def test_sala_planner_mapping_renames_expected_keys() -> None:
    sala = resolve_negotiation_context("sala_reuniones")
    adapter = load_prompt_io_adapter(sala.prompt_io_mapping_path)

    payload = {
        "schema_version": "planner_input.v1",
        "negotiation_brief": {
            "contexto_de_mercado": {"valor_estimado": "alta"},
            "realidad_de_la_alternativa": {"coste_equivalente_aproximado": "medio"},
        },
        "negotiation_state": {
            "last_offer_self": {"price_amount": 1, "currency": "EUR"},
            "last_offer_other": {"price_amount": 2, "currency": "EUR"},
            "tentative_agreement": {"price_amount": 3, "currency": "EUR"},
        },
    }

    adapted = adapter.adapt_input_payload("planner", deepcopy(payload))
    adapted_text = json.dumps(adapted, ensure_ascii=False)
    assert "resource_context" in adapted_text
    assert "estimated_availability" in adapted_text
    assert "allocation_amount" in adapted_text
    assert "allocation_unit" in adapted_text


def test_missing_mapping_file_fails_explicitly(tmp_path: Path) -> None:
    missing = tmp_path / "missing_mapping.json"
    with pytest.raises(PromptIOMappingError):
        load_prompt_io_adapter(missing)


def test_invalid_mapping_schema_unknown_field_fails_explicitly(tmp_path: Path) -> None:
    invalid = {
        "schema_version": "prompt_io_mapping.v1",
        "nodes": {
            "planner": {
                "inputs": {
                    "unknown_field": {"rename": "x"}
                }
            }
        },
    }
    path = tmp_path / "invalid_mapping.json"
    path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PromptIOMappingError):
        load_prompt_io_adapter(path)


def test_mapping_disabled_does_not_remove_context_skew_signal() -> None:
    skew_on = _scenario(REPORT, "skew_sala_over_validacion_enabled")
    skew_off = _scenario(REPORT, "skew_sala_over_validacion_mapping_off")

    assert skew_on["requested_context_id"] == "sala_reuniones"
    assert skew_off["requested_context_id"] == "sala_reuniones"
    assert skew_on["trace_context_meta"]["context_id"] == "validacion_multicontexto"
    assert skew_off["trace_context_meta"]["context_id"] == "validacion_multicontexto"

    planner_chars_on = skew_on["node_prompt_stats"]["planner"]["payload_chars"]
    planner_chars_off = skew_off["node_prompt_stats"]["planner"]["payload_chars"]
    assert abs(planner_chars_on - planner_chars_off) < 100


def test_mapping_changes_field_names_only_when_enabled() -> None:
    clean_on = _scenario(REPORT, "clean_sala_enabled")
    clean_off = _scenario(REPORT, "clean_sala_mapping_off")

    planner_on = [e for e in clean_on["mapping_transform_events"] if e["node"] == "planner"]
    planner_off = [e for e in clean_off["mapping_transform_events"] if e["node"] == "planner"]

    assert planner_on and any(e["changed"] for e in planner_on)
    assert planner_off and all(not e["changed"] for e in planner_off)


def test_session_bound_context_mismatch_is_observable_in_probe() -> None:
    skew = _scenario(REPORT, "skew_sala_over_validacion_enabled")
    assert skew["requested_context_id"] == "sala_reuniones"
    assert skew["session_bound_context_id"] == "validacion_multicontexto"
