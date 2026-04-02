from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import bind_context_to_session, resolve_negotiation_context
from negociacion.orchestration.context_errors import ContextMismatchError
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.orchestration.turn_execution_context import TurnExecutionContext
from sessions.state import SessionState


def test_execute_turn_with_contract_blocks_mismatch_before_runtime() -> None:
    state = SessionState(user_id="u", session_id="s")
    bind_context_to_session(state=state, context=resolve_negotiation_context("baseline_current"))

    config = build_negotiation_pipeline_config(context_id="baseline_current", stateful=True)
    bad_turn_context = TurnExecutionContext(
        user_id="u",
        session_id="s",
        execution_mode="stateful",
        effective_context_id="sala_reuniones",
        requested_context_id="sala_reuniones",
        session_bound_context_id="baseline_current",
        context_source="internal_explicit",
        entry_surface="tests",
        entrypoint="/tests",
    )

    with pytest.raises(ContextMismatchError):
        execute_turn_with_contract(
            state=state,
            user_message="hola",
            config=config,
            contract=TurnEntryContract(
                entry_surface="tests",
                entrypoint="/tests",
                overrides_applied=False,
                optimizer_wrapper_used=False,
            ),
            turn_context=bad_turn_context,
        )
