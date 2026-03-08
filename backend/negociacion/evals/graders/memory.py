from __future__ import annotations

from typing import Any

from ...nodes.memory_node import MemoryOutput

from .common import EvalCaseResult, build_case_result, check


STOPWORDS = {"el", "la", "los", "las", "de", "del", "y", "o", "que", "mi", "tu", "su", "es", "un", "una", "con"}


def _keywords(text: str) -> set[str]:
    return {token.strip(".,:;!?¿¡").lower() for token in text.split() if len(token.strip(".,:;!?¿¡")) > 3 and token.strip(".,:;!?¿¡").lower() not in STOPWORDS}


def grade_memory_case(case_id: str, output_payload: dict[str, Any], expected_checks: dict[str, Any], case_input: dict[str, Any] | None = None) -> EvalCaseResult:
    checks = []
    notes: list[str] = []
    try:
        output = MemoryOutput.model_validate(output_payload)
        checks.append(check("output_schema_valid", True))
    except Exception as exc:
        checks.append(check("output_schema_valid", False, str(exc)))
        return build_case_result("memory", case_id, checks)

    summary = (output.working_memory_new.last_turn_summary or "").strip()
    checks.append(check("working_memory_last_turn_summary_non_empty", bool(summary)))
    checks.append(check("working_memory_current_topic_present", output.working_memory_new.current_topic is None or bool(output.working_memory_new.current_topic.strip())))

    if expected_checks.get("require_episodic_append"):
        checks.append(check("episodic_append_non_empty", len(output.episodic_append) > 0))

    if expected_checks.get("forbid_duplicate_event_types"):
        event_types = [item.event_type for item in output.episodic_append]
        checks.append(check("episodic_append_no_duplicate_event_types", len(set(event_types)) == len(event_types)))

    if expected_checks.get("require_pending_question"):
        checks.append(check("pending_question_present", bool((output.working_memory_new.pending_question or "").strip())))

    if expected_checks.get("forbid_empty_summary"):
        checks.append(check("last_turn_summary_non_empty", bool(summary)))

    filler_tokens = ["jaja", "mmm", "ehh", "relleno"]
    checks.append(check("summary_without_obvious_filler", not any(tok in summary.lower() for tok in filler_tokens)))

    if expected_checks.get("forbid_duplicate_event_summaries"):
        summaries = [item.event_summary.strip().lower() for item in output.episodic_append]
        checks.append(check("episodic_append_no_duplicate_event_summaries", len(set(summaries)) == len(summaries)))

    if case_input is not None:
        user_turn = case_input.get("user_turn", {}) if isinstance(case_input, dict) else {}
        user_text = (user_turn.get("normalized_text") or user_turn.get("raw_text") or "") if isinstance(user_turn, dict) else ""
        if expected_checks.get("require_factual_overlap") and user_text:
            overlap = len(_keywords(user_text).intersection(_keywords(summary)))
            checks.append(check("summary_basic_factual_overlap_with_user_turn", overlap > 0, f"overlap={overlap}"))

        if expected_checks.get("require_pending_question") and isinstance(user_text, str) and user_text:
            pending_q = (output.working_memory_new.pending_question or "").strip()
            checks.append(check("pending_question_format", pending_q.endswith("?") if pending_q else False))

    return build_case_result("memory", case_id, checks, notes=notes)
