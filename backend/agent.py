from __future__ import annotations

from typing import Tuple

from chat import run_chat_agent
from sessions.state import SessionState


def run_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    """Compat wrapper: chat now runs on the OpenAI production 3-LLM pipeline."""
    return run_chat_agent(state, user_message)
