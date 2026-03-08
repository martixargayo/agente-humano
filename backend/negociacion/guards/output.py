from __future__ import annotations

import openai

from ..nodes.executor_node import ExecutorOutput
from ..nodes.memory_node import UserTurn
from ..nodes.planner_node import PlannerOutput
from . import constants
from .builders import apply_safe_output, build_output_block_response, build_output_rewrite_response
from .input import _detect_pii
from .models import OutputGuardrailDecision, OutputGuardrailResult, PlannerContractSignals
from .moderation import has_high_risk_moderation_flags, run_moderation_check
from .policy import GuardrailsPolicy


def _detected_internal_terms(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _detected_overclaims(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _planner_contract_signals(planner_output: PlannerOutput, executor_output: ExecutorOutput) -> PlannerContractSignals:
    violations: list[str] = []
    if planner_output.status == "clarify" and executor_output.status == "deliver":
        violations.append("clarify_should_not_deliver_definitive")
    if planner_output.status == "refuse" and executor_output.status != "refuse":
        violations.append("refuse_should_not_deliver")
    if planner_output.status == "plan" and executor_output.status == "refuse":
        violations.append("plan_mismatch_refuse")
    return PlannerContractSignals(planner_status=planner_output.status, executor_status=executor_output.status, violations=violations)


def run_output_guardrails(*, executor_output: ExecutorOutput, planner_output: PlannerOutput, user_turn: UserTurn, policy: GuardrailsPolicy, client: openai.OpenAI | None) -> tuple[ExecutorOutput, OutputGuardrailResult]:
    if not policy.output_guardrails_enabled:
        result = OutputGuardrailResult(
            decision=OutputGuardrailDecision.allow,
            reasons=[],
            status_before=executor_output.status,
            status_after=executor_output.status,
            planner_contract_signals=_planner_contract_signals(planner_output, executor_output),
        )
        return executor_output, result

    reasons: list[str] = []
    decision = OutputGuardrailDecision.allow
    internal_terms = _detected_internal_terms(executor_output.spoken_text, policy.internal_language_terms)
    pii = _detect_pii(executor_output.spoken_text)
    overclaims = _detected_overclaims(executor_output.spoken_text, policy.overclaim_terms)
    contract = _planner_contract_signals(planner_output, executor_output)
    moderation = run_moderation_check(client=client, text=executor_output.spoken_text, enabled=policy.allow_moderation_for_output and policy.moderation_enabled)

    if internal_terms:
        reasons.append("internal_language_guardrail")
        decision = OutputGuardrailDecision.rewrite
    if pii.matched_keywords or pii.matched_patterns:
        reasons.append("pii_output_guardrail")
        decision = OutputGuardrailDecision.rewrite
    if len(pii.matched_patterns) >= 2:
        reasons.append("pii_output_high_risk")
        decision = OutputGuardrailDecision.block
    if overclaims:
        reasons.append("overclaim_guardrail")
        if decision == OutputGuardrailDecision.allow:
            decision = OutputGuardrailDecision.rewrite
    if contract.violations:
        reasons.append("planner_contract_guardrail")
        if decision == OutputGuardrailDecision.allow:
            decision = OutputGuardrailDecision.rewrite

    unsafe_output = any(term in executor_output.spoken_text.lower() for term in constants.UNSAFE_OUTPUT_TERMS)
    if moderation.flagged_categories or unsafe_output:
        reasons.append("unsafe_content_output_guardrail")
        if decision == OutputGuardrailDecision.allow:
            decision = OutputGuardrailDecision.rewrite
    if has_high_risk_moderation_flags(moderation.flagged_categories):
        decision = OutputGuardrailDecision.block

    adjusted = executor_output
    rewrite_applied = False
    if decision == OutputGuardrailDecision.rewrite:
        adjusted = apply_safe_output(executor_output, rewritten_text=build_output_rewrite_response(), refusal_reason="guardrail_rewrite")
        rewrite_applied = True
    elif decision == OutputGuardrailDecision.block:
        adjusted = apply_safe_output(executor_output, rewritten_text=build_output_block_response(), status="refuse", refusal_reason="guardrail_block")
        rewrite_applied = True

    if moderation.unavailable_reason and policy.moderation_enabled:
        reasons.append(f"output_moderation_not_used:{moderation.unavailable_reason}")

    result = OutputGuardrailResult(
        decision=decision,
        reasons=sorted(set(reasons)),
        status_before=executor_output.status,
        status_after=adjusted.status,
        rewrite_applied=rewrite_applied,
        detected_internal_terms=internal_terms,
        pii_signals=pii,
        overclaim_signals=overclaims,
        planner_contract_signals=contract,
        moderation_used=moderation.used,
        moderation_flags=moderation.flagged_categories,
    )
    _ = user_turn
    return adjusted, result
