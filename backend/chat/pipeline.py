from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from openai_production import PipelineConfig, run_three_llm_turn
from state import SessionState

BASE_DIR = Path(__file__).resolve().parent


def run_chat_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = PipelineConfig(
        memory_key="chat_memory",
        prompts_dir=BASE_DIR / "prompts",
        planner_schema_path=Path(__file__).resolve().parent.parent / "openai_production" / "schemas" / "planner_output.schema.json",
        planner_model=os.getenv("CHAT_PLANNER_MODEL", "gpt-5-nano"),
        summarizer_model=os.getenv("CHAT_SUMMARIZER_MODEL", "gpt-5-nano"),
        executor_model=os.getenv("CHAT_EXECUTOR_MODEL", "gpt-5-nano"),
        context_limit=int(os.getenv("CHAT_CONTEXT_LIMIT", "6")),
        keep_last_n_turns=int(os.getenv("CHAT_KEEP_LAST_TURNS", "3")),
    )
    return run_three_llm_turn(state, user_message, config)
