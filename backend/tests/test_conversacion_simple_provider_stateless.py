from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.pipeline import _call_brain_structured, _call_summarizer_structured


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None
        self.output_text = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(id="resp_1", output_text=self.output_text)


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_call_brain_structured_keeps_provider_call_stateless() -> None:
    client = _FakeClient()
    client.responses.output_text = '{"schema_version":"brain.v1","status":"deliver","assistant_response":{"text":"ok"},"state_patch":{"conversation_state":{"phase":"desarrollo","status":"active","current_turn_goal":"x"},"memory_working":{"current_topic":null,"pending_question":null,"last_turn_summary":"ok"},"memory_episodic_append":[]}}'
    _ = _call_brain_structured(
        client=client,
        model="gpt-5-nano",
        messages=[{"role": "developer", "content": "d"}, {"role": "user", "content": "u"}],
    )
    kwargs = client.responses.kwargs
    assert kwargs is not None
    assert kwargs["store"] is False
    assert "conversation_id" not in kwargs
    assert "previous_response_id" not in kwargs


def test_call_summarizer_structured_keeps_provider_call_stateless() -> None:
    client = _FakeClient()
    client.responses.output_text = '{"schema_version":"memory_summary.v1","situation_live":"ok","active_proposal":null,"latest_offer_each_side":[],"concessions_accumulated":[],"open_items":[],"closed_items":[],"operative_constraints":[],"fixed_time_calculations":[],"operative_question_live":null,"sensitive_info_exposed":[],"agreement_progress":null,"pending_inconsistencies":[],"uncertainties":[]}'
    _ = _call_summarizer_structured(
        client=client,
        model="gpt-5.4-nano",
        messages=[{"role": "developer", "content": "d"}, {"role": "user", "content": "u"}],
    )
    kwargs = client.responses.kwargs
    assert kwargs is not None
    assert kwargs["store"] is False
    assert "conversation_id" not in kwargs
    assert "previous_response_id" not in kwargs
