from __future__ import annotations

import os

from ..cases import load_jsonl_cases
from ..graders.executor import grade_executor_case
from . import print_summary, summarize_results
from .live_utils import run_live_executor


DATASET = "executor_live_cases.jsonl"


def run() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("[executor_live] skipped: OPENAI_API_KEY is required for real model execution")
        return 2

    cases = load_jsonl_cases(DATASET)
    results = []
    for case in cases:
        executor_input, planner_status, output = run_live_executor(case)
        results.append(grade_executor_case(case["case_id"], output, planner_status, case.get("expected_checks", {}), executor_input))
    summary = summarize_results("executor_live", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
