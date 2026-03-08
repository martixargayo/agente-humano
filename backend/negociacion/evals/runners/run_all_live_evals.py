from __future__ import annotations

from .run_end_to_end_live_evals import run as run_end_to_end_live
from .run_executor_live_evals import run as run_executor_live
from .run_memory_live_evals import run as run_memory_live
from .run_phase_live_evals import run as run_phase_live
from .run_planner_live_evals import run as run_planner_live


def run() -> int:
    exit_codes = {
        "phase_live": run_phase_live(),
        "memory_live": run_memory_live(),
        "planner_live": run_planner_live(),
        "executor_live": run_executor_live(),
        "end_to_end_live": run_end_to_end_live(),
    }
    failed = [name for name, code in exit_codes.items() if code == 1]
    skipped = [name for name, code in exit_codes.items() if code == 2]
    print(f"[all_live_evals] failed_families={failed} skipped_families={skipped}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
