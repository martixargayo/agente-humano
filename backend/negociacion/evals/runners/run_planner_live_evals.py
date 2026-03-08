from __future__ import annotations

import os

from ..cases import load_jsonl_cases
from ..graders.planner import grade_planner_case
from . import print_summary, summarize_results
from .live_utils import run_live_planner


DATASET = "planner_live_cases.jsonl"


def run() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("[planner_live] skipped: OPENAI_API_KEY is required for real model execution")
        return 2

    cases = load_jsonl_cases(DATASET)
    results = []
    for case in cases:
        planner_input, output = run_live_planner(case)
        results.append(
            grade_planner_case(
                case["case_id"],
                output,
                case.get("expected_checks", {}),
                case.get("allowed_decisions", []),
                case.get("forbidden_decisions", []),
                planner_input,
            )
        )
    summary = summarize_results("planner_live", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
