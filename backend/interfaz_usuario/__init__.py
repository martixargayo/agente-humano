from __future__ import annotations

from fastapi import APIRouter

from . import services
from evaluacion.api import router as feedback_router
from .models import NegotiationTurnRequest, NegotiationTurnResponse, SessionBootstrapRequest

# Parity-safe surface for negotiation turns.
# This router is intentionally independent from avatar_app legacy mode switching
# and does not route through /chat or /negociar legacy endpoints.
router = APIRouter(prefix="/api/interfaz_usuario", tags=["interfaz_usuario"])
router.include_router(feedback_router)


@router.post("/sessions/bootstrap")
def bootstrap_session(payload: SessionBootstrapRequest) -> dict:
    return services.ensure_session(user_id=payload.user_id, session_id=payload.session_id)


@router.post("/negociacion/new_conversation")
def new_conversation(payload: SessionBootstrapRequest) -> dict:
    return services.create_new_conversation(user_id=payload.user_id, base_session_id=payload.session_id)


@router.post("/negociacion/turn", response_model=NegotiationTurnResponse)
def negotiation_turn(payload: NegotiationTurnRequest) -> NegotiationTurnResponse:
    result = services.run_turn(
        user_id=payload.user_id,
        session_id=payload.session_id,
        message=payload.message,
        new_conversation=payload.new_conversation,
    )
    return NegotiationTurnResponse(**result)
