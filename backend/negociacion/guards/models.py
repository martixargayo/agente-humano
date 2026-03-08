from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class InputGuardrailDecision(str, Enum):
    allow = "allow"
    soft_restrict = "soft_restrict"
    block = "block"


class OutputGuardrailDecision(str, Enum):
    allow = "allow"
    rewrite = "rewrite"
    block = "block"


class ModerationSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    used: bool = False
    unavailable_reason: str | None = None
    flagged_categories: list[str] = Field(default_factory=list)


class InjectionSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched_terms: list[str] = Field(default_factory=list)


class PIISignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched_keywords: list[str] = Field(default_factory=list)
    matched_patterns: list[str] = Field(default_factory=list)


class TaskFitSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    empty_input: bool = False
    spam_signals: list[str] = Field(default_factory=list)
    off_scope: bool = False


class PlannerContractSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planner_status: str
    executor_status: str
    violations: list[str] = Field(default_factory=list)


class InputGuardrailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: InputGuardrailDecision
    reasons: list[str] = Field(default_factory=list)
    moderation_used: bool = False
    moderation_flags: list[str] = Field(default_factory=list)
    injection_signals: InjectionSignals = Field(default_factory=InjectionSignals)
    pii_signals: PIISignals = Field(default_factory=PIISignals)
    task_fit_signals: TaskFitSignals = Field(default_factory=TaskFitSignals)


class OutputGuardrailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: OutputGuardrailDecision
    reasons: list[str] = Field(default_factory=list)
    status_before: str
    status_after: str
    rewrite_applied: bool = False
    detected_internal_terms: list[str] = Field(default_factory=list)
    pii_signals: PIISignals = Field(default_factory=PIISignals)
    overclaim_signals: list[str] = Field(default_factory=list)
    planner_contract_signals: PlannerContractSignals
    moderation_used: bool = False
    moderation_flags: list[str] = Field(default_factory=list)
