from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.forensics_multicontext_silent_collapse import build_report

REPORT = build_report()


def _top_context(markers: dict[str, int]) -> str:
    return max(markers.items(), key=lambda item: item[1])[0]


def test_phase_assets_follow_requested_context() -> None:
    for scenario in REPORT["scenarios"].values():
        for turn in scenario["turns"]:
            requested = turn["requested_context_id"]
            for asset_kind in ["phase_classifier_card", "phase_cards"]:
                entries = turn["resolved_assets"][asset_kind]
                assert entries, f"missing_asset_resolution:{asset_kind}"
                for entry in entries:
                    dominant = _top_context(entry["markers"])
                    assert dominant == requested, (
                        f"asset_context_mismatch asset={asset_kind} requested={requested} dominant={dominant} markers={entry['markers']}"
                    )


def test_detects_state_bleed_between_contexts_in_same_session() -> None:
    scenario = REPORT["scenarios"]["validacion_then_sala"]
    second_turn = scenario["turns"][1]
    planner_markers = second_turn["node_payloads"]["planner"]["markers"]
    executor_markers = second_turn["node_payloads"]["executor"]["markers"]

    assert planner_markers["validacion_multicontexto"] > planner_markers["sala_reuniones"]
    assert executor_markers["validacion_multicontexto"] > executor_markers["sala_reuniones"]


def test_context_assets_immutable_after_alternating_loads() -> None:
    assert REPORT["asset_hashes_mutated"] is False
