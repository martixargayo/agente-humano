from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from conversacion_simple.nodes.common import UserTurn


class ConversationSimpleNodeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str
    model_called: bool
    model_attempted: bool = False
    model_succeeded: bool = False
    latency_ms: int
    status: str
    fallback_reason_code: str | None = None
    input_summary: dict[str, object] = Field(default_factory=dict)
    output_summary: dict[str, object] = Field(default_factory=dict)


class ConversationSimpleTurnTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_version: str = "conversation_simple.trace.v1"
    pipeline_topology: str = "single_llm"
    turn_id: str
    timestamp_utc: str
    session_id: str
    user_id: str | None = None
    conversation_id_before: str | None = None
    conversation_id_after: str | None = None
    previous_response_id_before: str | None = None
    previous_response_id_after: str | None = None
    user_turn: UserTurn
    final_reply_text: str
    final_status: str
    brain_model_attempted: bool = False
    brain_model_succeeded: bool = False
    brain_fallback_reason_code: str | None = None
    context_id: str | None = None
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)
    memory_observability: dict[str, object] = Field(default_factory=dict)
    nodes: dict[str, ConversationSimpleNodeTrace] = Field(default_factory=dict)
    runtime_version: dict[str, str | None] = Field(default_factory=dict)
