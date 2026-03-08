from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

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

    guardrails_triggered: bool
    guardrail_reasons: list[str]
    guardrail_rewrite_applied: bool
    guardrail_status_before: str
    guardrail_status_after: str

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

    # Ordered execution timeline, useful for latency/status sequencing.
    logs: List[RichNodeTrace]
    # Indexed access by node name for direct grading lookups.
    nodes: dict[Literal["memory", "phase_classifier", "planner", "executor"], RichNodeTrace]
