from __future__ import annotations

import os

from sessions.state import SessionState

from ..cases import load_jsonl_cases
from ..graders.end_to_end import grade_end_to_end_case
from . import print_summary, summarize_results
from ...orchestration.flow_config import build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from ...state.canonical_state import build_default_canonical_state


DATASET = "end_to_end_live_cases.jsonl"


def run() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("[end_to_end_live] skipped: OPENAI_API_KEY is required for real model execution")
        return 2

    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False, "feature_traces": True})
    cases = load_jsonl_cases(DATASET)
    results = []

    for case in cases:
        init = case.get("initial_state", {})
        session = SessionState(user_id=init.get("user_id", "eval_live_user"), session_id=init.get("session_id", case["case_id"]))
        session.history.extend(case.get("recent_dialogue", []))
        session.world_state[config.memory_key] = build_default_canonical_state(
            session_id=session.session_id,
            user_id=session.user_id,
            thread_mode=config.thread_mode_default,
        ).model_dump(mode="json")

        reply, updated = run_negotiation_cognitive_turn(session, case["user_message"], config)

        results.append(
            grade_end_to_end_case(
                case_id=case["case_id"],
                final_reply=reply,
                world_state=updated.world_state,
                memory_key=config.memory_key,
                expected_checks=case.get("expected_checks", {}),
            )
        )

    summary = summarize_results("end_to_end_live", results)
    print_summary(summary)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
