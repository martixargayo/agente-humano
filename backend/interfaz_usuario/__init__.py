from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import services
from evaluacion.api import router as feedback_router
from .models import (
    NegotiationTurnRequest,
    NegotiationTurnResponse,
    SessionBootstrapRequest,
    SessionBootstrapResponse,
    SessionFinalizeRequest,
    SessionFinalizeResponse,
)

# Parity-safe surface for negotiation turns.
# This router is intentionally independent from avatar_app legacy mode switching
# and does not route through /chat or /negociar legacy endpoints.
router = APIRouter(prefix="/api/interfaz_usuario", tags=["interfaz_usuario"])
router.include_router(feedback_router)


@router.post("/sessions/bootstrap", response_model=SessionBootstrapResponse)
def bootstrap_session(payload: SessionBootstrapRequest) -> SessionBootstrapResponse:
    return SessionBootstrapResponse(**services.ensure_session(
        user_id=payload.user_id,
        session_id=payload.session_id,
        context_id=payload.context_id,
        public_slug=payload.public_slug,
    ))


@router.post("/negociacion/new_conversation")
def new_conversation(payload: SessionBootstrapRequest) -> dict:
    if not payload.user_id or not payload.session_id:
        raise HTTPException(status_code=400, detail="session_identity_required")
    return services.create_new_conversation(user_id=payload.user_id, base_session_id=payload.session_id)


@router.post("/sessions/finalize", response_model=SessionFinalizeResponse)
def finalize_session(payload: SessionFinalizeRequest) -> SessionFinalizeResponse:
    return SessionFinalizeResponse(**services.finalize_session(user_id=payload.user_id, session_id=payload.session_id, reason=payload.reason))


@router.post("/negociacion/turn", response_model=NegotiationTurnResponse)
def negotiation_turn(payload: NegotiationTurnRequest) -> NegotiationTurnResponse:
    result = services.run_turn(
        user_id=payload.user_id,
        session_id=payload.session_id,
        message=payload.message,
        new_conversation=payload.new_conversation,
    )
    return NegotiationTurnResponse(**result)
