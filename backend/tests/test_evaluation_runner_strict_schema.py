from __future__ import annotations

import json

from evaluacion.contracts.models import TurnTrajectoryV1
from evaluacion.engine.runners.common import run_structured


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.output_text = json.dumps(payload, ensure_ascii=False)


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> _FakeResponse:
        self.last_kwargs = kwargs
        return _FakeResponse(
            {
                "schema_version": "turn_trajectory.v1",
                "trajectory": [],
                "conviction_level_0_100": None,
            }
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesApi()


def test_run_structured_normalizes_required_fields_for_strict_json_schema(monkeypatch) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr("evaluacion.engine.runners.common._client", lambda: fake_client)

    parsed = run_structured(
        model="gpt-test",
        developer_prompt="Dev prompt",
        user_payload={"schema_version": "trajectory_runner_input.v1"},
        output_model=TurnTrajectoryV1,
        schema_name="turn_trajectory_v1",
    )

    assert parsed is not None
    assert parsed["conviction_level_0_100"] is None

    assert fake_client.responses.last_kwargs is not None
    text = fake_client.responses.last_kwargs["text"]
    format_payload = text["format"]
    schema = format_payload["schema"]
    root_required = schema.get("required", [])

    assert "conviction_level_0_100" in root_required
