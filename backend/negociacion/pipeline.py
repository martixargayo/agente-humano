from __future__ import annotations

from pathlib import Path
from typing import Tuple

from openai_production import PipelineConfig, run_three_llm_turn
from state import SessionState

BASE_DIR = Path(__file__).resolve().parent

# Configuración local del nodo de negociación (sin depender de variables .env).
NEGOTIATION_PLANNER_MODEL = "gpt-5-nano"
NEGOTIATION_SUMMARIZER_MODEL = "gpt-5-nano"
NEGOTIATION_EXECUTOR_MODEL = "gpt-5-nano"
NEGOTIATION_CONTEXT_LIMIT = 6
NEGOTIATION_KEEP_LAST_TURNS = 3


def run_negotiation_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = PipelineConfig(
        memory_key="negotiation_memory",
        prompts_dir=BASE_DIR / "prompts",
        planner_schema_path=Path(__file__).resolve().parent.parent / "openai_production" / "schemas" / "planner_output.schema.json",
        planner_model=NEGOTIATION_PLANNER_MODEL,
        summarizer_model=NEGOTIATION_SUMMARIZER_MODEL,
        executor_model=NEGOTIATION_EXECUTOR_MODEL,
        context_limit=NEGOTIATION_CONTEXT_LIMIT,
        keep_last_n_turns=NEGOTIATION_KEEP_LAST_TURNS,
    )
    return run_three_llm_turn(state, user_message, config)
