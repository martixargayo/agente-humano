from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.forensics_runtime_broken_route_map import build_report


REPORT = build_report()


def _route(route_id: str) -> dict:
    for item in REPORT["routes"]:
        if item["route_id"] == route_id:
            return item
    raise AssertionError(f"route_not_found:{route_id}")


def test_direct_execute_turn_contract_is_blocked_pre_execution() -> None:
    route = _route("direct_execute_turn_contract")
    assert route["result"]["admitted"] is False
    assert route["result"]["status"] == 400
    assert route["result"]["blocked_stage"] == "pre_execution"
    assert route["first_mismatch"] is None


def test_pipeline_run_negotiation_agent_default_is_broken_when_bound_differs() -> None:
    route = _route("pipeline_run_negotiation_agent_default")
    assert route["result"]["admitted"] is False
    assert route["result"]["status"] == 400


def test_interfaz_route_blocks_context_switch_with_409() -> None:
    route = _route("interfaz_ensure_session_conflict")
    assert route["result"]["admitted"] is False
    assert route["result"]["status"] == 409


def test_optimizer_route_blocks_context_switch_with_409() -> None:
    route = _route("optimizer_ensure_session_conflict")
    assert route["result"]["admitted"] is False
    assert route["result"]["status"] == 409


def test_static_inventory_covers_production_callers() -> None:
    inventory = REPORT["static_inventory"]
    execute_files = {item["file"] for item in inventory["execute_turn_with_contract_callers"]}
    run_files = {item["file"] for item in inventory["run_negotiation_cognitive_turn_callers"]}

    assert "interfaz_usuario/services.py" in execute_files
    assert "negociacion/optimizador/services.py" in execute_files
    assert "negociacion/pipeline.py" in run_files
    assert "negociacion/orchestration/turn_contract.py" in run_files

    negotiation_agent_files = {item["file"] for item in inventory["run_negotiation_agent_callers"]}
    assert "api/app.py" not in negotiation_agent_files


def test_api_negociar_legacy_endpoint_now_requires_explicit_context() -> None:
    route = _route("api_negociar_legacy_endpoint")
    assert route["result"]["admitted"] is False
    assert route["result"]["status"] in {400, 422}
