# backend/negotiation/progress_updater.py
from __future__ import annotations

from .elementos.execution_definitions import OUTCOME_GOOD, OUTCOME_NEUTRAL
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_plan_ledger,
    default_progress_state,
)
from .world_state_updater import diff_world_state


def _has_info_delta(world_diff: dict) -> bool:
    if not isinstance(world_diff, dict):
        return False
    return any(key != "interaction" for key in world_diff.keys())


def _evaluate_outcome(
    policy_id: str,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
) -> str:
    del prev_belief_state, belief_state
    if not policy_id:
        return OUTCOME_NEUTRAL
    world_diff = diff_world_state(prev_world_state, world_state)
    return OUTCOME_GOOD if bool(world_diff) else OUTCOME_NEUTRAL


def _extract_current_intent_id(active_plan: dict | None) -> str:
    if not isinstance(active_plan, dict):
        return ""
    steps = active_plan.get("steps") if isinstance(active_plan.get("steps"), list) else []
    if not steps:
        return ""
    try:
        idx = int(active_plan.get("current_step_idx", 0) or 0)
    except Exception:
        idx = 0
    idx = max(0, min(idx, len(steps) - 1))
    step = steps[idx] if isinstance(steps[idx], dict) else {}
    return str(step.get("intent_id", "") or "").strip()[:64]


def _best_judge_evidence(policy_plan_judgement: dict | None, user_message: str) -> str:
    if isinstance(policy_plan_judgement, dict):
        evidence = policy_plan_judgement.get("evidence")
        if isinstance(evidence, list) and evidence:
            first = evidence[0] if isinstance(evidence[0], dict) else {}
            quote = str(first.get("quote", "") or "").strip()
            if quote:
                return quote[:220]
    return str(user_message or "").strip()[:220]


def _upsert_resolved_intent(ledger: dict, *, intent_id: str, evidence: str, turn_idx: int) -> None:
    resolved = ledger.get("resolved_intents") if isinstance(ledger.get("resolved_intents"), list) else []
    replaced = False
    for item in resolved:
        if isinstance(item, dict) and str(item.get("intent_id", "")) == intent_id:
            item["evidence"] = evidence
            item["turn_idx"] = int(turn_idx)
            replaced = True
            break
    if not replaced:
        resolved.append({"intent_id": intent_id, "evidence": evidence, "turn_idx": int(turn_idx)})
    ledger["resolved_intents"] = resolved[-30:]


def _upsert_failed_intent(ledger: dict, *, intent_id: str, reason: str, attempts: int, turn_idx: int) -> None:
    failed = ledger.get("failed_intents") if isinstance(ledger.get("failed_intents"), list) else []
    replaced = False
    for item in failed:
        if isinstance(item, dict) and str(item.get("intent_id", "")) == intent_id:
            item["reason"] = reason
            item["attempts"] = int(attempts)
            item["turn_idx"] = int(turn_idx)
            replaced = True
            break
    if not replaced:
        failed.append(
            {
                "intent_id": intent_id,
                "reason": reason[:180],
                "attempts": int(attempts),
                "turn_idx": int(turn_idx),
            }
        )
    ledger["failed_intents"] = failed[-30:]




def _extract_question_text(text: str) -> str:
    body = str(text or "").strip()
    if not body or "?" not in body:
        return ""
    chunks = [seg.strip() for seg in body.split("?") if seg.strip()]
    if not chunks:
        return ""
    return (chunks[-1] + "?")[:180]


def _record_recent_question(ledger: dict, executor_output: dict | None, last_assistant_message: str) -> None:
    question_text = ""
    if isinstance(executor_output, dict) and bool(executor_output.get("asked_question", False)):
        question_text = _extract_question_text(str(executor_output.get("response_text", "") or ""))
    if not question_text:
        question_text = _extract_question_text(last_assistant_message)
    if not question_text:
        return
    recent = [str(x).strip() for x in (ledger.get("asked_questions_recent") if isinstance(ledger.get("asked_questions_recent"), list) else []) if str(x).strip()]
    if question_text in recent:
        recent = [x for x in recent if x != question_text]
    recent.append(question_text)
    ledger["asked_questions_recent"] = recent[-10:]

def _update_plan_ledger(
    *,
    ledger: dict,
    policy_plan_judgement: dict | None,
    active_plan: dict | None,
    user_message: str,
    turn_count: int,
    executor_output: dict | None = None,
    last_assistant_message: str = "",
) -> dict:
    out = default_plan_ledger()
    out.update(ledger if isinstance(ledger, dict) else {})
    out.setdefault("resolved_intents", [])
    out.setdefault("open_intents", [])
    out.setdefault("failed_intents", [])
    out.setdefault("asked_questions_recent", [])
    out.setdefault("attempt_counters", {})

    _record_recent_question(out, executor_output, last_assistant_message)

    intent_id = _extract_current_intent_id(active_plan)
    if not intent_id or not isinstance(policy_plan_judgement, dict):
        return out

    counters = out.get("attempt_counters") if isinstance(out.get("attempt_counters"), dict) else {}
    counters[intent_id] = int(counters.get(intent_id, 0) or 0) + 1
    out["attempt_counters"] = counters

    status = str(policy_plan_judgement.get("plan_status", "") or "")
    if status in {"advance_step", "completed"}:
        evidence = _best_judge_evidence(policy_plan_judgement, user_message)
        _upsert_resolved_intent(out, intent_id=intent_id, evidence=evidence, turn_idx=turn_count)
        return out

    if status == "continue_same_step":
        attempts = int(counters.get(intent_id, 0) or 0)
        if attempts >= 2:
            reason = str(
                policy_plan_judgement.get("why")
                or policy_plan_judgement.get("degrade_reason")
                or "no_progress"
            )[:180]
            _upsert_failed_intent(
                out,
                intent_id=intent_id,
                reason=reason,
                attempts=attempts,
                turn_idx=turn_count,
            )
        return out

    if status == "interrupted_replan":
        reason = str(
            policy_plan_judgement.get("why")
            or policy_plan_judgement.get("degrade_reason")
            or "interrupted_replan"
        )[:180]
        _upsert_failed_intent(
            out,
            intent_id=intent_id,
            reason=reason,
            attempts=int(counters.get(intent_id, 0) or 0),
            turn_idx=turn_count,
        )

    return out


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
    last_policy_executed: PolicyDecision | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
    turn_count: int = 0,
    include_debug: bool = False,
    policy_plan_judgement: dict | None = None,
    user_message: str = "",
    active_plan: dict | None = None,
    executor_output: dict | None = None,
    last_assistant_message: str = "",
) -> ProgressState | tuple[ProgressState, dict]:
    progress = default_progress_state()
    if prev_progress:
        progress.update(prev_progress)

    previous_policy_id = last_policy_executed.get("policy_id", "") if last_policy_executed else ""
    if previous_policy_id:
        outcome = _evaluate_outcome(
            previous_policy_id,
            prev_world_state,
            world_state,
            prev_belief_state,
            belief_state,
        )
        progress["last_executed_policy_id"] = previous_policy_id
        progress["last_executed_policy_outcome"] = outcome
        last_by_policy = dict(progress.get("policy_last_outcome", {}))
        last_by_policy[previous_policy_id] = outcome
        progress["policy_last_outcome"] = last_by_policy

    policy_id = policy_decision.get("policy_id", "")
    if policy_id:
        attempts = dict(progress.get("policy_attempts", {}))
        attempts[policy_id] = attempts.get(policy_id, 0) + 1
        progress["policy_attempts"] = attempts

        last_chosen_policy_id = progress.get("last_chosen_policy_id", "")
        if last_chosen_policy_id == policy_id:
            progress["turns_in_same_mode"] = int(progress.get("turns_in_same_mode", 0) or 0) + 1
        else:
            progress["turns_in_same_mode"] = 1
        progress["last_chosen_policy_id"] = policy_id

    loop_flags = [str(flag) for flag in progress.get("loop_flags", []) if str(flag).strip()]

    active_plan = active_plan if isinstance(active_plan, dict) else (
        progress.get("active_plan") if isinstance(progress.get("active_plan"), dict) else None
    )
    current_plan_id = str((active_plan or {}).get("plan_id", ""))
    prev_plan_id = str(progress.get("last_plan_id", ""))
    if current_plan_id and prev_plan_id and current_plan_id != prev_plan_id:
        plan_changes = int(progress.get("plan_id_changes_window", 0) or 0) + 1
    else:
        plan_changes = max(0, int(progress.get("plan_id_changes_window", 0) or 0) - 1)
    progress["plan_id_changes_window"] = plan_changes
    progress["last_plan_id"] = current_plan_id

    if plan_changes >= 2 and "replan_churn" not in loop_flags:
        loop_flags.append("replan_churn")
    if plan_changes < 2:
        loop_flags = [flag for flag in loop_flags if flag != "replan_churn"]

    judgement = progress.get("last_judgement_status")
    no_progress = int(progress.get("no_progress_same_step_turns", 0) or 0)
    if judgement == "continue_same_step":
        no_progress += 1
    else:
        no_progress = 0
    progress["no_progress_same_step_turns"] = no_progress
    if no_progress >= 3 and "continue_loop" not in loop_flags:
        loop_flags.append("continue_loop")
    if no_progress < 3:
        loop_flags = [flag for flag in loop_flags if flag != "continue_loop"]

    stuck_in_policy_now = int(progress.get("turns_in_same_mode", 0) or 0) >= 2 and progress.get("last_executed_policy_outcome") != OUTCOME_GOOD
    if stuck_in_policy_now and "stuck_in_policy" not in loop_flags:
        loop_flags.append("stuck_in_policy")
    if not stuck_in_policy_now:
        loop_flags = [flag for flag in loop_flags if flag != "stuck_in_policy"]

    progress["loop_flags"] = loop_flags
    progress["last_progress_update_turn"] = turn_count

    progress["plan_ledger"] = _update_plan_ledger(
        ledger=progress.get("plan_ledger") if isinstance(progress.get("plan_ledger"), dict) else {},
        policy_plan_judgement=policy_plan_judgement,
        active_plan=active_plan,
        user_message=user_message,
        turn_count=turn_count,
        executor_output=executor_output,
        last_assistant_message=last_assistant_message,
    )

    if not include_debug:
        return progress

    debug = {
        "anti_loop_signals": {
            "continue_loop_detected": "continue_loop" in loop_flags,
            "continue_loop_counter": int(progress.get("no_progress_same_step_turns", 0) or 0),
            "replan_churn_detected": "replan_churn" in loop_flags,
            "replan_churn_window": int(progress.get("plan_id_changes_window", 0) or 0),
            "plan_id_changes_count": int(progress.get("plan_id_changes_window", 0) or 0),
            "judgement_missing_streak": int(progress.get("judgement_missing_streak", 0) or 0),
        },
        "plan_ledger": {
            "resolved_count": len((progress.get("plan_ledger") or {}).get("resolved_intents", [])),
            "failed_count": len((progress.get("plan_ledger") or {}).get("failed_intents", [])),
        },
    }
    return progress, debug
