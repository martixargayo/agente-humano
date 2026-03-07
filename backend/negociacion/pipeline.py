from __future__ import annotations

from typing import Tuple

from sessions.state import SessionState

from .orchestration.cognitive_architecture import run_negotiation_cognitive_turn
from .orchestration.flow_config import build_negotiation_pipeline_config


def run_negotiation_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = build_negotiation_pipeline_config()
    return run_negotiation_cognitive_turn(state, user_message, config)
