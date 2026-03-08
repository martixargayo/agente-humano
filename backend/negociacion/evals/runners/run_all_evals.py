from __future__ import annotations

"""Runs fixture/contract eval families (deterministic layer)."""

from .run_end_to_end_mock_evals import run as run_end_to_end_mock
from .run_executor_fixture_evals import run as run_executor_fixture
from .run_memory_fixture_evals import run as run_memory_fixture
from .run_phase_fixture_evals import run as run_phase_fixture
from .run_planner_fixture_evals import run as run_planner_fixture


def run() -> int:
    exit_codes = {
        "memory_fixture": run_memory_fixture(),
        "phase_fixture": run_phase_fixture(),
        "planner_fixture": run_planner_fixture(),
        "executor_fixture": run_executor_fixture(),
        "end_to_end_mock": run_end_to_end_mock(),
    }
    failed = [name for name, code in exit_codes.items() if code != 0]
    print(f"[all_fixture_evals] failed_families={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
