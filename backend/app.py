# backend/app.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from state import get_session_state
from agent import run_agent

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
