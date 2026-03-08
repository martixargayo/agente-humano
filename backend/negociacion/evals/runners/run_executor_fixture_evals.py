from __future__ import annotations

from ..cases import load_jsonl_cases
from ..graders.executor import grade_executor_case
from . import print_summary, summarize_results


DATASET = "executor_fixture_cases.jsonl"


def run() -> int:
    cases = load_jsonl_cases(DATASET)
    results = [
        grade_executor_case(
            case["case_id"],
            case["candidate_output"],
            case["planner_output_status"],
            case.get("expected_checks", {}),
            case.get("input"),
        )
        for case in cases
    ]
    summary = summarize_results("executor_fixture", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
