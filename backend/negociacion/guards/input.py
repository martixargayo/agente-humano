from __future__ import annotations

import re

import openai

from . import constants
from .models import InputGuardrailDecision, InputGuardrailResult, InjectionSignals, PIISignals, TaskFitSignals
from .moderation import has_high_risk_moderation_flags, run_moderation_check
from .policy import GuardrailsPolicy


def _detect_injection(text: str, terms: list[str]) -> InjectionSignals:
    lower = text.lower()
    return InjectionSignals(matched_terms=[term for term in terms if term in lower])


def _detect_pii(text: str) -> PIISignals:
    lower = text.lower()
    keywords = [term for term in constants.PII_KEYWORDS if term in lower]
    patterns: list[str] = []
    if constants.DNI_REGEX.search(text):
        patterns.append("dni_pattern")
    if constants.IBAN_REGEX.search(text):
        patterns.append("iban_pattern")
    if constants.PASSPORT_REGEX.search(text):
        patterns.append("passport_pattern")
    if constants.CARD_REGEX.search(text):
        patterns.append("card_pattern")
    if re.search(r"\bcvv\b", lower) and constants.CVV_REGEX.search(text):
        patterns.append("cvv_pattern")
    return PIISignals(matched_keywords=keywords, matched_patterns=patterns)


def _detect_task_fit(text: str) -> TaskFitSignals:
    cleaned = " ".join(text.split()).strip()
    lower = cleaned.lower()
    spam = [t for t in constants.TASK_FIT_SPAM_TERMS if t in lower]
    off_scope = "negoci" not in lower and any(token in lower for token in ["hack", "malware", "ddos"])
    return TaskFitSignals(empty_input=not bool(cleaned), spam_signals=spam, off_scope=off_scope)


def run_input_guardrails(*, user_text: str, policy: GuardrailsPolicy, client: openai.OpenAI | None) -> InputGuardrailResult:
    """Evaluate input guardrails. In v1, soft_restrict is only a caution marker (no hard pipeline mutation)."""
    if not policy.input_guardrails_enabled:
        return InputGuardrailResult(decision=InputGuardrailDecision.allow)

    reasons: list[str] = []
    decision = InputGuardrailDecision.allow

    moderation = run_moderation_check(client=client, text=user_text, enabled=policy.allow_moderation_for_input and policy.moderation_enabled)
    injection = _detect_injection(user_text, policy.injection_terms)
    pii = _detect_pii(user_text)
    task_fit = _detect_task_fit(user_text)

    if moderation.flagged_categories:
        reasons.append("input_moderation_flags")
        decision = InputGuardrailDecision.soft_restrict
    if has_high_risk_moderation_flags(moderation.flagged_categories):
        decision = InputGuardrailDecision.block
        reasons.append("input_moderation_high_risk")

    if injection.matched_terms:
        reasons.append("prompt_injection_signal")
        if decision != InputGuardrailDecision.block:
            decision = InputGuardrailDecision.soft_restrict
    if len(injection.matched_terms) >= 2 and pii.matched_patterns:
        decision = InputGuardrailDecision.block
        reasons.append("combined_injection_sensitive")

    pii_score = len(pii.matched_keywords) + len(pii.matched_patterns)
    if pii_score:
        reasons.append("pii_input_signal")
        if decision != InputGuardrailDecision.block:
            decision = InputGuardrailDecision.soft_restrict
    if pii_score >= 3:
        decision = InputGuardrailDecision.block
        reasons.append("pii_input_high_risk")

    if task_fit.empty_input:
        decision = InputGuardrailDecision.block
        reasons.append("task_fit_empty")
    elif task_fit.spam_signals or task_fit.off_scope:
        reasons.append("task_fit_low_quality")
        if decision == InputGuardrailDecision.allow:
            decision = InputGuardrailDecision.soft_restrict

    if moderation.unavailable_reason and policy.moderation_enabled:
        reasons.append(f"input_moderation_not_used:{moderation.unavailable_reason}")

    return InputGuardrailResult(
        decision=decision,
        reasons=sorted(set(reasons)),
        moderation_used=moderation.used,
        moderation_flags=moderation.flagged_categories,
        injection_signals=injection,
        pii_signals=pii,
        task_fit_signals=task_fit,
    )
