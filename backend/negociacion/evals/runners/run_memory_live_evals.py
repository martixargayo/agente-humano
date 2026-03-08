from __future__ import annotations

import os

from ..cases import load_jsonl_cases
from ..graders.memory import grade_memory_case
from . import print_summary, summarize_results
from .live_utils import run_live_memory


DATASET = "memory_live_cases.jsonl"


def run() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("[memory_live] skipped: OPENAI_API_KEY is required for real model execution")
        return 2

    cases = load_jsonl_cases(DATASET)
    results = []
    for case in cases:
        output = run_live_memory(case)
        synthetic_input = {"user_turn": {"normalized_text": case["user_message"]}}
        results.append(grade_memory_case(case["case_id"], output, case.get("expected_checks", {}), synthetic_input))
    summary = summarize_results("memory_live", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
