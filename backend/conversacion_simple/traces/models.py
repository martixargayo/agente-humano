from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConversationSimpleNodeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str
    model_called: bool
    latency_ms: int
    status: str
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
    final_reply_text: str
    final_status: str
    context_id: str | None = None
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)
    memory_observability: dict[str, object] = Field(default_factory=dict)
    nodes: dict[str, ConversationSimpleNodeTrace] = Field(default_factory=dict)
