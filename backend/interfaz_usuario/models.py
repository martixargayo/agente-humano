from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SessionBootstrapRequest(BaseModel):
    user_id: str = "u_interfaz"
    session_id: str = "interfaz-main"


class NegotiationTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    session_id: str
    message: str
    new_conversation: bool = False


class EntryConfigSnapshot(BaseModel):
    memory_key: str
    thread_mode_default: str
    model_memory: str
    model_phase_classifier: str
    model_planner: str
    model_executor: str
    max_recent_messages: int
    max_executor_recent_turns: int


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
