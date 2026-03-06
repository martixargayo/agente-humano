from __future__ import annotations

from typing import Tuple

from state import SessionState

from .cognitive_architecture import run_negotiation_cognitive_turn
from .flow_config import build_negotiation_pipeline_config


def run_negotiation_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = build_negotiation_pipeline_config()
    return run_negotiation_cognitive_turn(state, user_message, config)
