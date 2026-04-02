from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.contexts import bind_context_to_session, resolve_negotiation_context
from negociacion.orchestration.context_errors import MissingTurnContextError
from negociacion.orchestration.flow_config import StateRepository, build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from sessions.state import SessionState


def test_stateful_runtime_blocks_before_load_state_when_validated_context_missing(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    bind_context_to_session(state=state, context=resolve_negotiation_context("baseline_current"))
    config = build_negotiation_pipeline_config(context_id="baseline_current", stateful=True)

    called = {"load_state": False}

    def _fail_load_state(*args, **kwargs):
        called["load_state"] = True
        raise AssertionError("load_state_should_not_run")

    monkeypatch.setattr(StateRepository, "load_state", _fail_load_state)

    with pytest.raises(MissingTurnContextError):
        run_negotiation_cognitive_turn(state, "hola", config, validated_context=None)

    assert called["load_state"] is False
