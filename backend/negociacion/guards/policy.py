from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from . import constants


class GuardrailsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "guardrails.v1.soft"
    input_guardrails_enabled: bool = True
    output_guardrails_enabled: bool = True
    moderation_enabled: bool = True
    allow_moderation_for_input: bool = True
    allow_moderation_for_output: bool = True
    injection_terms: list[str] = constants.INJECTION_TERMS
    internal_language_terms: list[str] = constants.INTERNAL_LANGUAGE_TERMS
    overclaim_terms: list[str] = constants.OVERCLAIM_TERMS


def build_guardrails_policy(*, feature_input_guardrails: bool, feature_output_guardrails: bool, feature_moderation: bool) -> GuardrailsPolicy:
    return GuardrailsPolicy(
        input_guardrails_enabled=feature_input_guardrails,
        output_guardrails_enabled=feature_output_guardrails,
        moderation_enabled=feature_moderation,
        allow_moderation_for_input=feature_moderation,
        allow_moderation_for_output=feature_moderation,
    )
