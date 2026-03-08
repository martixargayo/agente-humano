from __future__ import annotations

from ..cases import load_jsonl_cases
from ..graders.phase import grade_phase_case
from . import print_summary, summarize_results


DATASET = "phase_fixture_cases.jsonl"


def run() -> int:
    cases = load_jsonl_cases(DATASET)
    results = [grade_phase_case(case["case_id"], case["candidate_output"], case["expected_phase"]) for case in cases]
    summary = summarize_results("phase_fixture", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
