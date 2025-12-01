# backend/app.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from state import get_session_state
from agent import run_agent

from negotiation.negotiation_graph import run_negotiation_agent


app = FastAPI(title="Agente Humano - MVP")


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    try:
        state = get_session_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

        reply, _ = run_agent(state, payload.message)
        return ChatResponse(reply=reply)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente: {e}",
        )

@app.post("/negociar", response_model=ChatResponse)
def negociar_endpoint(payload: ChatRequest):
    """
    Endpoint específico para el agente NEGOCIADOR (comprador de coche).

    Usa el mismo sistema de sesión (user_id + session_id),
    pero pasa la conversación por el grafo de LangGraph
    con planner + executor.
    """
    try:
        state = get_session_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

        reply, _ = run_negotiation_agent(state, payload.message)
        return ChatResponse(reply=reply)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno en el agente de negociación: {e}",
        )
