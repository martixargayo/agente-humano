from __future__ import annotations

from typing import Tuple

from sessions.state import SessionState

from .orchestration.flow_config import build_negotiation_pipeline_config
from .orchestration.turn_service import run_negotiation_turn_canonical
from .state.shared_types import NegotiationChannel, NegotiationExecutionProfile


def run_negotiation_agent(state: SessionState, user_message: str) -> Tuple[str, SessionState]:
    config = build_negotiation_pipeline_config()
    result = run_negotiation_turn_canonical(
        state=state,
        user_message=user_message,
        config=config,
        channel=NegotiationChannel.avatar,
        execution_profile=NegotiationExecutionProfile.canonical_negotiation,
    )
    return result.reply, result.updated_state
