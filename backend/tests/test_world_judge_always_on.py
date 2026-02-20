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


def test_world_judge_degrades_progress_without_evidence_and_injects_audit_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"advance_step","why":"ok","evidence":[],"confidence":0.9,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="vale, adelante",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert judgement["plan_status"] == "continue_same_step"
    assert judgement["degrade_reason"] == "missing_evidence_for_progress"
    assert len(judgement["evidence"]) >= 1


def test_world_judge_payload_includes_context_fields_and_evidence_candidates(monkeypatch):
    captured = {"payload": None}

    class _CaptureModel:
        def invoke(self, messages):
            captured["payload"] = messages[1].content
            return _FakeResp('{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[],"confidence":0.5,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}')

    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _CaptureModel())
    world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{"success_criteria": ["x"]}]},
        user_message="u",
        objective="obj",
        world_state={},
        recent_history="hist",
        turn_count=2,
        assistant_last_message="a",
        memory_short="ms",
        memory_long="ml",
        progress_state={"no_progress_same_step_turns": 3, "loop_flags": ["continue_loop"]},
    )
    assert captured["payload"] is not None
    assert '"assistant_last_message": "a"' in captured["payload"]
    assert '"memory_short": "ms"' in captured["payload"]
    assert '"memory_long": "ml"' in captured["payload"]
    assert '"progress_counters"' in captured["payload"]
    assert '"evidence_candidates"' in captured["payload"]


def test_world_judge_constraint_message_injects_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[],"confidence":0.7,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="no puedo pagar más de 12k",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert len(judgement["evidence"]) >= 1
    assert judgement["evidence"][0]["source"] == "user_message"
    assert meta["judge_evidence_injected"] is True


def test_world_judge_question_message_injects_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[],"confidence":0.6,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="¿tienes facturas?",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert len(judgement["evidence"]) >= 1


def test_world_judge_acceptance_keeps_evidence_for_progress_status(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"completed","why":"ok","evidence":[{"quote":"vale, acepto 12k","source":"user_message"}],"confidence":0.9,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="vale, acepto 12k",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert judgement["plan_status"] == "completed"
    assert len(judgement["evidence"]) >= 1


def test_world_judge_empty_user_message_can_have_empty_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[],"confidence":0.5,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="   ",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
        assistant_last_message="",
    )
    assert judgement["evidence"] == []
    assert meta["judge_evidence_missing"] is True


def test_world_judge_missing_signals_requires_evidence(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[],"confidence":0.5,"missing_signals":["confirmar_precio_final"],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="necesito más detalles",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert len(judgement["evidence"]) >= 1
    assert meta["judge_missing_signals_without_evidence"] is False


def test_world_judge_repairs_malformed_evidence_shape(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[{"quote":"","source":"bad"},{"quote":"texto útil","source":"invalid_source","span":["a",2]}],"confidence":0.7,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="mensaje útil",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=1,
    )
    assert len(judgement["evidence"]) >= 1
    assert judgement["evidence"][0]["quote"] != ""
    assert judgement["evidence"][0]["source"] in {"user_message", "assistant_last_message", "recent_history", "world_state"}


def test_world_judge_loop_forces_interrupted_replan(monkeypatch):
    content = '{"schema_version":"v1","plan_status":"continue_same_step","why":"ok","evidence":[{"quote":"x","source":"user_message"}],"confidence":0.8,"missing_signals":[],"safety_flags":[],"degraded":false,"degrade_reason":""}'
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _FakeModel(content=content))
    judgement, _meta = world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{}]},
        user_message="seguimos",
        objective="obj",
        world_state={},
        recent_history="",
        turn_count=4,
        progress_state={"no_progress_same_step_turns": 3},
    )
    assert judgement["plan_status"] == "interrupted_replan"
    assert judgement["degrade_reason"] == "loop_same_step_threshold"
