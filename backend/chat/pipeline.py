from __future__ import annotations

from pathlib import Path
from typing import Tuple

from openai_production import PipelineConfig, run_three_llm_turn
from state import SessionState

BASE_DIR = Path(__file__).resolve().parent

# Configuración local del nodo de chat (sin depender de variables .env).
CHAT_PLANNER_MODEL = "gpt-5-nano"
CHAT_SUMMARIZER_MODEL = "gpt-5-nano"
CHAT_EXECUTOR_MODEL = "gpt-5-nano"
CHAT_CONTEXT_LIMIT = 6
CHAT_KEEP_LAST_TURNS = 3


def run_chat_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = PipelineConfig(
        memory_key="chat_memory",
        prompts_dir=BASE_DIR / "prompts",
        planner_schema_path=Path(__file__).resolve().parent.parent / "openai_production" / "schemas" / "planner_output.schema.json",
        planner_model=CHAT_PLANNER_MODEL,
        summarizer_model=CHAT_SUMMARIZER_MODEL,
        executor_model=CHAT_EXECUTOR_MODEL,
        context_limit=CHAT_CONTEXT_LIMIT,
        keep_last_n_turns=CHAT_KEEP_LAST_TURNS,
    )
    return run_three_llm_turn(state, user_message, config)
