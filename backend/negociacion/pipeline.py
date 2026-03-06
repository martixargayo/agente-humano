from __future__ import annotations

from typing import Tuple

from openai_production import run_three_llm_turn
from state import SessionState

from .flow_config import build_negotiation_pipeline_config


def run_negotiation_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = build_negotiation_pipeline_config()
    return run_three_llm_turn(state, user_message, config)
