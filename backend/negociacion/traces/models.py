from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..nodes.memory_node import UserTurn
from ..state.shared_types import NodeName, SDKCompatibilityStatus, StructuredCallSource, ThreadMode
from .summaries import (
    ExecutorInputSummary,
    ExecutorOutputSummary,
    MemoryInputSummary,
    MemoryOutputSummary,
    PhaseInputSummary,
    PhaseOutputSummary,
    PlannerInputSummary,
    PlannerOutputSummary,
)


class StructuredCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parsed_json: dict | None
    refusal: str | None
    parse_error: str | None
    exception_error: str | None
    response: object | None
    source: StructuredCallSource
    model_called: bool = False
    raw_output_text: str | None = None


class EvalGrades(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planner_coherence: str
    executor_naturalness: str
    planner_executor_agreement: bool
    safety_compliance: bool


class SDKCompatibilityInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installed_version: str | None
    minimum_version: str
    status: SDKCompatibilityStatus
    details: str


NodeInputSummary = MemoryInputSummary | PhaseInputSummary | PlannerInputSummary | ExecutorInputSummary
NodeOutputSummary = MemoryOutputSummary | PhaseOutputSummary | PlannerOutputSummary | ExecutorOutputSummary


class TraceContextMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str | None = None
    context_id: str | None = None
    context_version: str | None = None
    official_context_used: bool = True
    context_scope: str | None = None


class PromptArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    developer_prompt_text: str | None = None
    user_prompt_rendered: str | None = None
    input_payload_json: str | None = None
    model_target: str
    prompt_version: str
    input_schema_version: str
    output_schema_version: str
    threading_policy: str | None = None
    threading_mode_effective: str | None = None
    developer_prompt_hash: str | None = None
    user_prompt_hash: str | None = None
    payload_hash: str | None = None
    developer_prompt_chars: int = 0
    user_prompt_chars: int = 0
    payload_chars: int = 0


class RichNodeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: NodeName
    node_name: str
    status: str
    source: StructuredCallSource
    latency_ms: int
    model_target: str
    prompt_version: str
    input_schema_version: str
    output_schema_version: str
    fallback_used: bool
    refusal_reason: str | None
    parse_error: str | None
    exception_type: str | None
    exception_message: str | None
    input_summary: NodeInputSummary
    output_summary: NodeOutputSummary
    model_called: bool = False
    validation_succeeded: bool = False
    fallback_applied: bool = False
    guardrail_applied: bool = False
    final_output_source: str = "unknown"
    status_before_guardrail: str | None = None
    status_after_guardrail: str | None = None
    output_changed_by_guardrail: bool = False
    raw_model_output_excerpt: str | None = None
    validated_output_summary: NodeOutputSummary | None = None
    fallback_output_summary: NodeOutputSummary | None = None
    post_guardrail_output_summary: NodeOutputSummary | None = None
    final_emitted_output_summary: NodeOutputSummary | None = None
    threading_policy: str | None = None
    threading_mode_effective: str | None = None
    request_context_has_conversation_id: bool = False
    request_context_has_previous_response_id: bool = False
    prompt_artifacts: PromptArtifacts | None = None


class TurnTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # compat + grading metadata
    trace_version: str
    turn_id: str
    timestamp_utc: str
    turn_started_at: str
    turn_finished_at: str
    total_latency_ms: int

    session_id: str
    user_id: str | None
    avatar_id: str | None
    thread_mode: ThreadMode

    conversation_id_before: str | None
    conversation_id_after: str | None
    previous_response_id_before: str | None
    previous_response_id_after: str | None

    user_turn: UserTurn
    final_reply_text: str
    final_reply_excerpt: str
    final_status: str
    assistant_turn_emitted: bool
    executor_reply_text_before_guardrail: str | None = None
    executor_status_before_guardrail: str | None = None
    executor_reply_changed_by_guardrail: bool = False
    final_output_source: str = "executor_post_guardrail"

    guardrails_triggered: bool
    guardrail_reasons: list[str]
    guardrail_rewrite_applied: bool
    guardrail_status_before: str
    guardrail_status_after: str

    input_guardrail_decision: str
    input_guardrail_reasons: list[str] = Field(default_factory=list)
    input_guardrail_triggered: bool = False
    input_moderation_used: bool = False
    input_moderation_flags: list[str] = Field(default_factory=list)

    output_guardrail_decision: str
    output_guardrail_reasons: list[str] = Field(default_factory=list)
    output_guardrail_triggered: bool = False
    output_guardrail_rewrite_applied: bool = False
    output_guardrail_enforcement_mode: str = "observe_only"
    output_guardrail_enforcement_action: str = "none"
    output_guardrail_observed_not_applied_rules: list[str] = Field(default_factory=list)
    output_guardrail_enforced_rules: list[str] = Field(default_factory=list)
    output_guardrail_output_changed: bool = False
    output_guardrail_status_before: str
    output_guardrail_status_after: str
    output_moderation_used: bool = False
    output_moderation_flags: list[str] = Field(default_factory=list)

    model_memory: str
    model_phase_classifier: str
    model_planner: str
    model_executor: str
    prompt_version_memory: str
    prompt_version_phase_classifier: str
    prompt_version_planner: str
    prompt_version_executor: str
    schema_version_memory: str
    schema_version_phase_classifier: str
    schema_version_planner: str
    schema_version_executor: str
    sdk_compatibility: SDKCompatibilityInfo
    grades: EvalGrades
    context_meta: TraceContextMeta | None = None

    # Ordered execution timeline, useful for latency/status sequencing.
    # When input_guardrail_decision=="block", cognitive nodes may not run and logs can be empty by design.
    logs: List[RichNodeTrace] = Field(default_factory=list)
    # Indexed access by node name for direct grading lookups.
    nodes: dict[Literal["memory", "phase_classifier", "planner", "executor"], RichNodeTrace] = Field(default_factory=dict)
