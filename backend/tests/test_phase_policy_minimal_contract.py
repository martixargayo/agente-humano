from types import SimpleNamespace

from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.nodes.world_node import world_judge_llm
from negotiation.phase_policy_planner import plan_phase_policy
from negotiation.schemas import default_belief_state, default_policy_state, default_progress_state, default_world_state


class _StructuredDummy:
    def invoke(self, _messages):
        return SimpleNamespace(
            model_dump=lambda: {
                "phase": "climate",
                "confidence": 0.7,
                "recovery_mode": False,
                "reasons": ["history:test"],
                "policy_id": "safe_neutral",
                "reason": "test",
                "micro_goal": "aclarar",
                "risk_posture": "low",
                "why_short": "ok",
                "active_plan": {
                    "plan_id": "plan_x",
                    "current_step_idx": 0,
                    "context_digest": "foco",
                    "steps": [
                        {"step_idx": 0, "goal": "g1", "success_criteria": ["s1"], "instruction": "i1"},
                        {"step_idx": 1, "goal": "g2", "success_criteria": ["s2"], "instruction": "i2"},
                    ],
                },
            }
        )


class _LlmDummy:
    def with_structured_output(self, _schema):
        return _StructuredDummy()


class _RetryStructuredDummy:
    def __init__(self):
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("Could not parse response content as the length limit was reached")
        return SimpleNamespace(
            model_dump=lambda: {
                "schema_version": "planner_v2",
                "phase": "interests",
                "recovery_mode": False,
                "policy_id": "safe_neutral",
                "active_plan": {
                    "plan_id": "plan_retry",
                    "current_step_idx": 0,
                    "context_digest": "foco",
                    "steps": [
                        {"step_idx": 0, "goal": "g1", "success_criteria": ["s1"], "instruction": "i1", "ask_slots": [], "stop_conditions": []},
                        {"step_idx": 1, "goal": "g2", "success_criteria": ["s2"], "instruction": "i2", "ask_slots": [], "stop_conditions": []},
                    ],
                },
                "executor_instruction": {
                    "plan_id": "plan_retry",
                    "step_idx": 0,
                    "instruction": "i1",
                    "ask_slots": ["detalle"],
                    "must_avoid": [],
                    "max_questions_per_turn": 1,
                    "language": "es",
                    "style_id": "psyplay_compact",
                },
            }
        )


class _RetryLlmDummy:
    def __init__(self):
        self.structured = _RetryStructuredDummy()
        self.bound_max_tokens = []

    def with_structured_output(self, _schema):
        return self.structured

    def bind(self, **kwargs):
        self.bound_max_tokens.append(kwargs.get("max_tokens"))
        return self


def test_plan_phase_policy_returns_minimal_active_plan_contract(monkeypatch):
    monkeypatch.setattr("negotiation.phase_policy_planner.get_planner_llm", lambda: _LlmDummy())
    phase_candidate, policy_decision, meta = plan_phase_policy(
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        policy_state={},
        policy_plan_summary={},
        objective="obj",
        constraints="",
        constraints_struct={},
        recent_context="",
        allowed_policy_ids=["safe_neutral"],
        advisor_recs={},
    )
    assert phase_candidate["phase"] == "climate"
    assert policy_decision["policy_id"] == "safe_neutral"
    assert isinstance(meta.get("active_plan"), dict)
    assert len(meta["active_plan"]["steps"]) >= 2


def test_plan_phase_policy_retries_once_on_truncation_with_higher_max_tokens(monkeypatch):
    retry_llm = _RetryLlmDummy()
    monkeypatch.setattr("negotiation.phase_policy_planner.get_planner_llm", lambda: retry_llm)
    phase_candidate, policy_decision, meta = plan_phase_policy(
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        policy_state={},
        policy_plan_summary={},
        objective="obj",
        constraints="",
        constraints_struct={},
        recent_context="",
        allowed_policy_ids=["safe_neutral"],
        advisor_recs={},
    )
    assert phase_candidate["phase"] == "interests"
    assert policy_decision["policy_id"] == "safe_neutral"
    assert meta["planner_retry_count"] == 1
    assert meta["planner_retry_reason"] == "length_limit_or_truncated_json"
    assert len(retry_llm.bound_max_tokens) == 1
    assert int(retry_llm.bound_max_tokens[0]) >= 1200


def test_executor_instruction_comes_from_planner_active_plan():
    def fake_plan_phase_policy(**_kwargs):
        return (
            {"phase": "climate", "confidence": 0.6, "reasons": [], "signals": [], "alternatives": []},
            {"policy_id": "safe_neutral", "reason": "r", "micro_goal": "m", "risk_posture": "low", "why_short": "w", "inputs_used": []},
            {
                "active_plan": {
                    "plan_id": "p1",
                    "current_step_idx": 0,
                    "steps": [
                        {
                            "step_idx": 0,
                            "intent_id": "step_1",
                            "micro_goal": "g",
                            "what_to_do": "instruccion del step",
                            "ask": [],
                            "success_criteria": ["x"],
                            "replan_triggers": [],
                            "safe_mode": "normal",
                        },
                        {
                            "step_idx": 1,
                            "intent_id": "step_2",
                            "micro_goal": "g2",
                            "what_to_do": "i2",
                            "ask": [],
                            "success_criteria": ["x2"],
                            "replan_triggers": [],
                            "safe_mode": "normal",
                        },
                    ],
                    "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
                }
            },
        )

    progress = default_progress_state()
    pstate = default_policy_state()
    pstate.update({"planner_request": "replan_policy"})
    progress["policy_state"] = pstate
    state = {
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": progress,
        "objective": "",
        "constraints": "",
        "hard_constraints_struct": {},
        "recent_history_text": "",
        "turn_count": 1,
        "world_diff": {},
        "belief_diff": {},
        "deps": SimpleNamespace(plan_phase_policy=fake_plan_phase_policy),
    }
    out = phase_policy_planner_node(state)
    assert out["executor_instruction"]["instruction"] == "instruccion del step"


def test_world_judge_reads_active_plan_current_step_with_mock_llm(monkeypatch):
    class _JudgeLLM:
        def invoke(self, _messages):
            return SimpleNamespace(
                content=(
                    '{"schema_version":"v1","plan_status":"continue_same_step",'
                    '"why":"ok","evidence":[{"quote":"ok","source":"user_message","span":[0,2]}],'
                    '"confidence":0.8,"missing_signals":[],"safety_flags":[],"degraded":false,'
                    '"degrade_reason":"","skip_planner":false}'
                )
            )

    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _JudgeLLM())
    active_plan = {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [{"what_to_do": "seguir"}, {"what_to_do": "cerrar"}],
    }
    judgement, meta = world_judge_llm(
        active_plan=active_plan,
        user_message="ok",
        objective="o",
        world_state=default_world_state(),
        recent_history="",
        turn_count=1,
    )
    assert judgement["plan_presence"] == "active"
    assert judgement["evaluated_step_idx"] == 0
    assert meta["judge_degraded"] is False
