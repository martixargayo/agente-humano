from __future__ import annotations

from negotiation.nodes.world_node import world_judge_llm


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeModel:
    def __init__(self, content: str = "", raises: bool = False):
        self._content = content
        self._raises = raises

    def invoke(self, _messages):
        if self._raises:
            raise RuntimeError("judge_down")
        return _FakeResp(self._content)


def test_world_judge_returns_valid_judgement_when_llm_ok(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[{"quote":"x","source":"user_message"}],"confidence":0.8,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":"","plan_id":"p1","evaluated_step_idx":0}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="hola",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert judgement["schema_version"] == "v1"
    assert judgement["plan_status"] == "continue_same_step"
    assert isinstance(meta["judge_latency_ms"], int)


def test_world_judge_fails_safe_never_none(monkeypatch):
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(raises=True))
    judgement, meta = world_judge_llm(
        active_plan=None,
        user_message="hola",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert judgement is not None
    assert judgement["schema_version"] == "v1"
    assert judgement["degraded"] is True
    assert judgement["plan_status"] == "interrupted_replan"
    assert meta["judge_error_type"] == "RuntimeError"


def test_world_judge_degrades_progress_without_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"advance_step","why":"ok","evidence":[],"confidence":0.9,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="hola",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert judgement["plan_status"] == "continue_same_step"
    assert judgement["degrade_reason"] == "missing_evidence_for_progress"
