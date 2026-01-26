# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import json
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from prompts import BELIEF_UPDATE_SYSTEM_PROMPT, BELIEF_UPDATE_USER_PROMPT
from .schemas import BeliefState, WorldState, default_belief_state


BELIEF_MODEL = os.getenv("BELIEF_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
BELIEF_TEMPERATURE = float(os.getenv("BELIEF_TEMPERATURE", "0.0"))

_belief_llm = ChatOpenAI(model=BELIEF_MODEL, temperature=BELIEF_TEMPERATURE)

_belief_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", BELIEF_UPDATE_SYSTEM_PROMPT),
        ("user", BELIEF_UPDATE_USER_PROMPT),
    ]
)


def update_belief_state(
    prev_belief_state: BeliefState | None,
    world_state: WorldState,
    user_message: str,
    context_snippet: str,
) -> BeliefState:
    previous = prev_belief_state or default_belief_state()

    messages = _belief_prompt.format_messages(
        prev_belief_state=json.dumps(previous, ensure_ascii=False),
        world_state=json.dumps(world_state, ensure_ascii=False),
        user_message=user_message,
        recent_history=context_snippet,
    )

    result = _belief_llm.invoke(messages)
    raw = (result.content or "").strip()

    try:
        data = json.loads(raw)
        return data  # type: ignore[return-value]
    except json.JSONDecodeError:
        print("[belief_state_updater] JSON inválido, usando estado previo.")
    except Exception as exc:
        print(f"[belief_state_updater] Error inesperado: {exc}")

    return previous
