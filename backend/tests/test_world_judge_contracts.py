from negotiation.nodes.world_node import _normalize_judgement, world_judge_llm


class _FakeResp:
    def __init__(self, content: str):
        self.content = content


class _FakeModel:
    def __init__(self, content: str):
        self.content = content
        self.model_name = "fake-judge"

    def invoke(self, _messages):
        return _FakeResp(self.content)


def test_skip_planner_forced_false_when_status_not_continue_same_step():
    normalized = _normalize_judgement(
        {
            "plan_status": "interrupted_replan",
            "skip_planner": True,
            "evidence": [{"quote": "cambiemos de tema", "source": "user_message"}],
        },
        active_plan={"plan_id": "p1"},
        turn_count=7,
    )
    assert normalized is not None
    assert normalized["skip_planner"] is False


def test_explicit_goal_change_forces_interrupted_replan_with_literal_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"interrupted_replan","why":"topic shift","evidence":[],"confidence":0.9,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":"","skip_planner":false}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{"success_criteria": ["cerrar precio"]}]},
        user_message="Olvida esto, cambiemos de tema: necesito otra cosa.",
        objective="cerrar trato",
        world_state={},
        recent_history="",
        turn_count=5,
    )
    assert judgement["plan_status"] == "interrupted_replan"
    assert judgement["evidence"]
    assert "Olvida esto" in judgement["evidence"][0]["quote"]


def test_normalize_judgement_forces_interrupted_replan_on_second_attempt():
    normalized = _normalize_judgement(
        {
            "plan_status": "continue_same_step",
            "skip_planner": True,
            "why": "sin novedad",
            "evidence": [{"quote": "igual", "source": "user_message"}],
        },
        active_plan={"plan_id": "p1"},
        turn_count=9,
        same_step_no_progress_turns=1,
    )
    assert normalized is not None
    assert normalized["plan_status"] == "interrupted_replan"
    assert normalized["skip_planner"] is False
    assert normalized["forced_replan_reason"] == "same_step_no_progress_2nd"
