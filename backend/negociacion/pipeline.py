from __future__ import annotations

from typing import Tuple
from typing import Literal

from sessions.state import SessionState

from .orchestration.cognitive_architecture import run_negotiation_cognitive_turn
from .orchestration.context_errors import ImplicitContextForbiddenError
from .orchestration.flow_config import build_negotiation_pipeline_config


def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    *,
    context_id: str | None = None,
    execution_mode: Literal["stateful", "non_stateful"] = "stateful",
) -> Tuple[str, SessionState]:
    if execution_mode == "stateful" and not (context_id or "").strip():
        raise ImplicitContextForbiddenError(message="run_negotiation_agent_requires_explicit_context")
    config = build_negotiation_pipeline_config(
        context_id=context_id,
        stateful=execution_mode == "stateful",
    )
    return run_negotiation_cognitive_turn(state, user_message, config)
