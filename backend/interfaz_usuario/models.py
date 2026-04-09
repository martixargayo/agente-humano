from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .presentation_models import PresentationConfig


class SessionBootstrapRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    context_id: str | None = None
    public_slug: str | None = None


class SessionBootstrapResponse(BaseModel):
    user_id: str
    session_id: str
    trace_count: int = 0
    last_updated: str
    session_bootstrap_state: str
    existing_session: bool = False
    conversation_id: str | None = None
    previous_response_id: str | None = None
    context_id: str
    public_slug: str
    presentation_config: PresentationConfig


class SessionFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    session_id: str
    reason: str | None = None


class SessionFinalizeResponse(BaseModel):
    user_id: str
    session_id: str
    status: str
    ttl_seconds: int
    last_updated: str


class NegotiationTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    session_id: str
    message: str
    new_conversation: bool = False


class EntryConfigSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    memory_key: str
    flow_id: str | None = None
    context_id: str | None = None
    brain_model_target: str | None = None
    summarizer_model_target: str | None = None
    context_limit_turns: int | None = None
    keep_last_n_turns: int | None = None
    recent_dialogue_short_max_messages: int | None = None
    episodic_compaction_trigger_count: int | None = None
    episodic_compaction_trigger_chars: int | None = None
    max_episodic_high_resolution_items: int | None = None
    maintenance_retry_limit: int | None = None
    compacted_summary_max_chars: int | None = None
    maintenance_force_failure: bool | None = None
    thread_mode_default: str | None = None
    model_memory: str | None = None
    model_phase_classifier: str | None = None
    model_planner: str | None = None
    model_executor: str | None = None
    max_recent_messages: int | None = None
    max_executor_recent_turns: int | None = None



class EntryContractPayload(BaseModel):
    entry_surface: str
    entrypoint: str
    overrides_applied: bool
    optimizer_wrapper_used: bool
    new_conversation: bool
    clone_used: bool
    config_snapshot: EntryConfigSnapshot


class NegotiationTurnResponse(BaseModel):
    reply: str
    user_id: str
    session_id: str
    trace_count: int = 0
    conversation_id_before: str | None = None
    conversation_id_after: str | None = None
    previous_response_id_before: str | None = None
    previous_response_id_after: str | None = None
    latest_turn_id: str | None = None
    entry_contract: EntryContractPayload
    auto_reset_applied: bool = False
    finish_button_armed: bool = False
    post_commit_housekeeping_error: str | None = None
    latency_breakdown_ms: dict[str, object] = Field(default_factory=dict)
