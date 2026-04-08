from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import experiments_bridge, services
from .models import BootstrapSessionRequest, CompareTurnsRequest, ConfirmOverridesRequest, NewConversationRequest, OverrideUpdateRequest, SandboxCloneRequest, SandboxTurnRequest, SaveCaseRequest

router = APIRouter(prefix="/api/optimizador", tags=["optimizador"])


@router.get("/sessions")
def list_sessions() -> dict:
    return {"items": services.list_sessions()}


@router.post("/sessions/bootstrap")
def bootstrap_session(payload: BootstrapSessionRequest) -> dict:
    return services.ensure_session(
        user_id=payload.user_id,
        session_id=payload.session_id,
        context_id=payload.context_id,
        flow_id=payload.flow_id,
    )


@router.get("/sessions/{user_id}/{session_id}/conversations")
def list_conversations(user_id: str, session_id: str) -> dict:
    return {"items": services.list_conversations(user_id, session_id)}


@router.get("/sessions/{user_id}/{session_id}/turns")
def list_turns(user_id: str, session_id: str, conversation_id: str | None = None) -> dict:
    return {"items": services.list_turns(user_id, session_id, conversation_id)}


@router.get("/sessions/{user_id}/{session_id}/dialogue")
def get_dialogue(user_id: str, session_id: str) -> dict:
    return {"items": services.get_dialogue(user_id, session_id)}


@router.get("/sessions/{user_id}/{session_id}/attempts")
def list_attempts(user_id: str, session_id: str) -> dict:
    return {"items": services.list_attempt_traces(user_id, session_id)}


@router.get("/turns/{turn_id}")
def get_turn(turn_id: str) -> dict:
    turn = services.get_turn(turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="turn no encontrado")
    return turn


@router.get("/turns/{turn_id}/guardrails")
def get_guardrails(turn_id: str) -> dict:
    payload = services.get_guardrails(turn_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="turn no encontrado")
    return payload


@router.get("/prompts")
def list_prompts(user_id: str | None = None, session_id: str | None = None, context_id: str | None = None) -> dict:
    try:
        return {"items": services.list_prompts(user_id=user_id, session_id=session_id, context_id=context_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/contexts")
def list_contexts(flow_id: str | None = None) -> dict:
    return {"items": services.list_contexts(flow_id=flow_id)}


@router.get("/overrides/{optimizer_session_id}")
def get_overrides(optimizer_session_id: str) -> dict:
    return experiments_bridge.get_state(optimizer_session_id)


@router.put("/overrides/{optimizer_session_id}")
def update_overrides(optimizer_session_id: str, payload: OverrideUpdateRequest) -> dict:
    try:
        return experiments_bridge.update_state(optimizer_session_id, payload.model_dump(mode="json", exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/overrides/{optimizer_session_id}/confirm")
def confirm_overrides(optimizer_session_id: str, payload: ConfirmOverridesRequest) -> dict:
    try:
        return experiments_bridge.confirm_state(optimizer_session_id, payload.model_dump(mode="json").get("entries", []))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/overrides/{optimizer_session_id}")
def reset_overrides(optimizer_session_id: str) -> dict:
    return experiments_bridge.reset_state(optimizer_session_id)


@router.post("/sandbox/clone")
def sandbox_clone(payload: SandboxCloneRequest) -> dict:
    try:
        return services.duplicate_sandbox_session(
            optimizer_session_id=payload.optimizer_session_id,
            source_user_id=payload.source_user_id,
            source_session_id=payload.source_session_id,
            source_conversation_id=payload.source_conversation_id,
            context_id=payload.context_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@router.post("/sandbox/new_conversation")
def sandbox_new_conversation(payload: NewConversationRequest) -> dict:
    return services.new_conversation_session(
        optimizer_session_id=payload.optimizer_session_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        context_id=payload.context_id,
    )

@router.post("/sandbox/turn")
def sandbox_turn(payload: SandboxTurnRequest) -> dict:
    return services.run_sandbox_turn(
        optimizer_session_id=payload.optimizer_session_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        scope_turn_id=payload.scope_turn_id,
        repeat_from_turn_id=payload.repeat_from_turn_id,
        client_request_id=payload.client_request_id,
        logical_user_message_id=payload.logical_user_message_id,
        logical_attempt_index=payload.logical_attempt_index,
    )


@router.post("/evals/{action}")
def run_eval(action: str) -> dict:
    try:
        return services.run_eval(action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cases")
def list_cases() -> dict:
    return {"items": services.list_cases()}


@router.post("/cases")
def save_case(payload: SaveCaseRequest) -> dict:
    try:
        return services.save_case(payload.turn_id, payload.family, payload.tags, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/compare")
def compare(payload: CompareTurnsRequest) -> dict:
    try:
        return services.compare_turns(payload.turn_a, payload.turn_b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
