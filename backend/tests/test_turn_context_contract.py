from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import bind_context_to_session, resolve_negotiation_context
from negociacion.orchestration.context_errors import ContextMismatchError, InvalidConfigContextError
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_context_validator import validate_turn_context_pre_execution
from negociacion.orchestration.turn_execution_context import TurnExecutionContext
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str) -> None:
    bind_context_to_session(state=state, context=resolve_negotiation_context(context_id))


def _turn_context(state: SessionState, context_id: str) -> TurnExecutionContext:
    return TurnExecutionContext(
        user_id=state.user_id,
        session_id=state.session_id,
        execution_mode="stateful",
        effective_context_id=context_id,
        requested_context_id=context_id,
        session_bound_context_id=context_id,
        context_source="internal_explicit",
        entry_surface="tests",
        entrypoint="/tests",
    )


def test_validator_accepts_coherent_stateful_context() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, "baseline_current")
    config = build_negotiation_pipeline_config(context_id="baseline_current", stateful=True)

    validated = validate_turn_context_pre_execution(
        state=state,
        config=config,
        turn_context=_turn_context(state, "baseline_current"),
    )

    assert validated.effective_context_id == "baseline_current"
    assert validated.session_bound_context_id == "baseline_current"
    assert validated.config_context_id == "baseline_current"


def test_validator_blocks_bound_effective_mismatch() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, "baseline_current")
    config = build_negotiation_pipeline_config(context_id="baseline_current", stateful=True)

    with pytest.raises(ContextMismatchError):
        validate_turn_context_pre_execution(
            state=state,
            config=config,
            turn_context=_turn_context(state, "sala_reuniones"),
        )


def test_validator_blocks_config_effective_mismatch() -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state, "baseline_current")
    config = build_negotiation_pipeline_config(context_id="sala_reuniones", stateful=True)

    with pytest.raises(InvalidConfigContextError):
        validate_turn_context_pre_execution(
            state=state,
            config=config,
            turn_context=_turn_context(state, "baseline_current"),
        )
