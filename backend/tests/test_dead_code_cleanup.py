import importlib
import sys
import warnings

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state, default_world_state
from negotiation.validation import normalize_progress_state
from state import SessionState


def _fake_deps():
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_update_skipped": False}

    def fake_execute(_messages):
        return "ok"

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_runtime_path_does_not_import_response_validator(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    state = SessionState(user_id="dead", session_id="dead")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=_fake_deps())

    assert "negotiation.response_validator" not in sys.modules
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert importlib.util.find_spec("negotiation.response_validator") is None


def test_constraints_struct_deprecated_warning():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", DeprecationWarning)
        normalize_progress_state({"constraints_struct": {"max_questions": 1}})
    assert any(
        "constraints_struct is deprecated" in str(item.message) for item in captured
    )
