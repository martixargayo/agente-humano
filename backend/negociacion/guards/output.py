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
    """Evaluate output guardrails with explicit observe-only semantics.

    In observe-only mode, non-critical rules are recorded but do not mutate user-visible output.
    Only critical rules can enforce rewrite/block.
    """
    if not policy.output_guardrails_enabled:
        result = OutputGuardrailResult(
            decision=OutputGuardrailDecision.allow,
            reasons=[],
            status_before=executor_output.status,
            status_after=executor_output.status,
            planner_contract_signals=_planner_contract_signals(planner_output, executor_output),
            enforcement_mode=policy.enforcement_mode,
            enforcement_action="none",
            output_changed=False,
        )
        return executor_output, result

    reasons: list[str] = []
    observed_rules: list[str] = []
    enforced_rules: list[str] = []
    internal_terms = _detected_internal_terms(executor_output.spoken_text, policy.internal_language_terms)
    pii = _detect_pii(executor_output.spoken_text)
    overclaims = _detected_overclaims(executor_output.spoken_text, policy.overclaim_terms)
    contract = _planner_contract_signals(planner_output, executor_output)
    moderation = run_moderation_check(client=client, text=executor_output.spoken_text, enabled=policy.allow_moderation_for_output and policy.moderation_enabled, stage="output")

    if internal_terms:
        reasons.append("internal_language_guardrail")
        observed_rules.append("internal_language_guardrail")
    if pii.matched_keywords or pii.matched_patterns:
        reasons.append("pii_output_guardrail")
        observed_rules.append("pii_output_guardrail")
    if len(pii.matched_patterns) >= 2:
        reasons.append("pii_output_high_risk")
        observed_rules.append("pii_output_high_risk")
    if overclaims:
        reasons.append("overclaim_guardrail")
        observed_rules.append("overclaim_guardrail")
    if contract.violations:
        reasons.append("planner_contract_guardrail")
        observed_rules.append("planner_contract_guardrail")

    unsafe_output = any(term in executor_output.spoken_text.lower() for term in constants.UNSAFE_OUTPUT_TERMS)
    if moderation.flagged_categories or unsafe_output:
        reasons.append("unsafe_content_output_guardrail")
        observed_rules.append("unsafe_content_output_guardrail")

    critical_triggered = {r for r in observed_rules if r in set(policy.critical_output_rules)}
    if has_high_risk_moderation_flags(moderation.flagged_categories):
        critical_triggered.add("unsafe_content_output_guardrail")

    adjusted = executor_output
    decision = OutputGuardrailDecision.allow
    rewrite_applied = False
    enforcement_action = "none"

    if critical_triggered:
        if "pii_output_high_risk" in critical_triggered or has_high_risk_moderation_flags(moderation.flagged_categories):
            decision = OutputGuardrailDecision.block
            adjusted = apply_safe_output(executor_output, rewritten_text=build_output_block_response(), status="refuse", refusal_reason="guardrail_block")
            rewrite_applied = True
            enforcement_action = "block_applied"
            enforced_rules = sorted(critical_triggered)
        else:
            decision = OutputGuardrailDecision.rewrite
            adjusted = apply_safe_output(executor_output, rewritten_text=build_output_rewrite_response(), refusal_reason="guardrail_rewrite")
            rewrite_applied = True
            enforcement_action = "rewrite_applied"
            enforced_rules = sorted(critical_triggered)
    elif observed_rules:
        enforcement_action = "observed_not_applied"

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
        enforcement_mode=policy.enforcement_mode,
        enforcement_action=enforcement_action,
        observed_not_applied_rules=sorted(set(observed_rules) - set(enforced_rules)),
        enforced_rules=enforced_rules,
        output_changed=(adjusted.spoken_text != executor_output.spoken_text or adjusted.status != executor_output.status),
    )
    _ = user_turn
    return adjusted, result
