from __future__ import annotations

import json

from negotiation import advisor
from negotiation.llm_planning_context import build_advisor_context_block_full, build_judge_context_block_full
from negotiation.nodes import world_node
from negotiation.repo_prompts import ADVISOR_V2_SYSTEM_PROMPT, WORLD_JUDGE_V2_SYSTEM_PROMPT


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeJudgeLLM:
    def __init__(self, *, plan_status: str = "continue_same_step"):
        self._plan_status = plan_status

    def invoke(self, _messages):
        return _FakeResponse(
            json.dumps(
                {
                    "schema_version": "v1",
                    "turn_idx": 1,
                    "plan_presence": "active",
                    "plan_id": "p1",
                    "evaluated_step_idx": 0,
                    "plan_status": self._plan_status,
                    "why": "Sin cierre explícito.",
                    "evidence": [{"quote": "Vendedor: aún no.", "source": "recent_history", "span": [0, 10]}],
                    "confidence": 0.6,
                    "missing_signals": [],
                    "safety_flags": [],
                    "degraded": False,
                    "degrade_reason": "",
                    "skip_planner": True,
                },
                ensure_ascii=False,
            )
        )


class _FakeAdvisorLLM:
    model_name = "fake"

    def invoke(self, _messages):
        return _FakeResponse(
            json.dumps(
                {
                    "diagnosis": ["ok"],
                    "loop_or_waste_flags": [],
                    "recommended_moves": [{"title": "t", "why": "w", "how": "h"}],
                    "guardrails": [{"if": "si", "then": "entonces"}],
                    "do_not_do": [],
                    "suggested_utterances": ["Perfecto, revisemos papeles."],
                },
                ensure_ascii=False,
            )
        )


def test_context_blocks_include_perspectiva_buyer():
    assert "PERSPECTIVA: buyer" in build_judge_context_block_full({})
    assert "PERSPECTIVA: buyer" in build_advisor_context_block_full({})


def test_world_judge_prompt_contains_full_profiles_and_speaker(monkeypatch):
    monkeypatch.setenv("USE_WORLD_JUDGE_V2", "0")
    monkeypatch.setattr(world_node, "get_planner_llm", lambda: _FakeJudgeLLM())
    judgement, meta = world_node.world_judge_llm(
        active_plan={
            "plan_id": "p1",
            "current_step_idx": 0,
            "steps": [{"instruction": "x", "success_criteria": ["a", "b"]}],
        },
        user_message="Comprador: entiendo",
        objective="",
        world_state={"world_buckets": {}},
        recent_history="Vendedor: te escucho",
        turn_count=1,
        progress_state={"speaker_of_last_message": "seller"},
        state={"speaker_of_last_message": "seller"},
    )
    assert judgement["schema_version"] == "v1"
    assert "WORLD_JUDGE_PROMPT_VARIANT: v2" in meta["judge_input_prompt_rendered"]
    assert meta["judge_prompt_variant"] == "v2"
    assert meta["use_world_judge_v2"] is True
    assert "BLOQUE_PERFILES_COMPLETOS" in meta["judge_input_prompt_rendered"]
    assert "SPEAKER_OF_LAST_MESSAGE: seller" in meta["judge_input_prompt_rendered"]
    assert "PERSPECTIVA: buyer" in meta["judge_input_prompt_rendered"]
    assert '["a", "b"]' in meta["judge_input_prompt_rendered"]


def test_world_judge_skip_planner_rule_prompt_present():
    assert "skip_planner=true SOLO si" in WORLD_JUDGE_V2_SYSTEM_PROMPT
    assert "pueden estar truncados" in WORLD_JUDGE_V2_SYSTEM_PROMPT


def test_v2_no_heuristic_speaker_call(monkeypatch):
    monkeypatch.setenv("USE_WORLD_JUDGE_V2", "0")
    monkeypatch.setenv("USE_ADVISOR_V2", "0")
    monkeypatch.setattr(world_node, "get_planner_llm", lambda: _FakeJudgeLLM())
    monkeypatch.setattr(advisor, "get_advisor_llm", lambda: _FakeAdvisorLLM())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("should_not_be_called")

    monkeypatch.setattr("negotiation.llm_planning_context.infer_speaker_of_last_message", _boom)

    world_node.world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{"instruction": "x", "success_criteria": "a"}]},
        user_message="hola",
        objective="",
        world_state={"world_buckets": {}},
        recent_history="Vendedor: te escucho",
        turn_count=1,
        progress_state={"speaker_of_last_message": "seller"},
        state={"speaker_of_last_message": "seller"},
    )

    advisor.build_advisor_recs(
        objective="",
        recent_history="Don Joaquín: puedo mostrar documentos mañana.",
        memory_short="",
        memory_long="",
        active_plan={"plan_id": "p"},
        progress_state={"speaker_of_last_message": "seller"},
        world_state={"world_buckets": {}},
        belief_state={"belief_buckets": {}},
        user_message="Perfecto, ¿nos vemos mañana?",
        state={"speaker_of_last_message": "seller"},
    )


def test_world_judge_defaults_speaker_to_seller_without_degrade(monkeypatch):
    monkeypatch.setenv("USE_WORLD_JUDGE_V2", "0")
    monkeypatch.setattr(world_node, "get_planner_llm", lambda: _FakeJudgeLLM(plan_status="advance_step"))
    judgement, _meta = world_node.world_judge_llm(
        active_plan={"plan_id": "p1", "current_step_idx": 0, "steps": [{"instruction": "x", "success_criteria": "a"}]},
        user_message="texto",
        objective="",
        world_state={"world_buckets": {}},
        recent_history="",
        turn_count=1,
        progress_state={},
        state={},
    )
    assert judgement["degraded"] is False


def test_advisor_prompt_contains_constraints_last_counterparty_and_user_message(monkeypatch):
    monkeypatch.setenv("USE_ADVISOR_V2", "0")
    monkeypatch.setattr(advisor, "get_advisor_llm", lambda: _FakeAdvisorLLM())
    recs, meta = advisor.build_advisor_recs(
        objective="",
        recent_history="Don Joaquín: puedo mostrar documentos mañana.",
        memory_short="",
        memory_long="",
        active_plan={"plan_id": "p"},
        progress_state={"speaker_of_last_message": "seller"},
        world_state={"world_buckets": {}},
        belief_state={"belief_buckets": {}},
        user_message="Me interesa, pero quiero verificar papeles.",
        state={"speaker_of_last_message": "seller"},
    )
    assert recs["diagnosis"] == ["ok"]
    assert "ADVISOR_PROMPT_VARIANT: v2" in meta["advisor_input_prompt_rendered"]
    assert meta["advisor_prompt_variant"] == "v2"
    assert meta["use_advisor_v2"] is True
    assert "BLOQUE_PERFILES_COMPLETOS" in meta["advisor_input_prompt_rendered"]
    assert "ULTIMA_FRASE_DEL_VENDEDOR" in meta["advisor_input_prompt_rendered"]
    assert "PERSPECTIVA: buyer" in meta["advisor_input_prompt_rendered"]
    assert "Me interesa, pero quiero verificar papeles." in meta["advisor_input_prompt_rendered"]
    assert meta["advisor_input_prompt_rendered"].count("[system]") == 1
    assert meta["advisor_input_prompt_rendered"].count("[human]") == 1


def test_advisor_world_full_json_is_compact(monkeypatch):
    monkeypatch.setenv("USE_ADVISOR_V2", "0")
    monkeypatch.setattr(advisor, "get_advisor_llm", lambda: _FakeAdvisorLLM())
    huge_world = {
        "world_state_meta": {"version": "v1"},
        "world_buckets": {"claims": [f"item-{i}" for i in range(1000)]},
    }
    _recs, meta = advisor.build_advisor_recs(
        objective="",
        recent_history="Don Joaquín: dato",
        memory_short="",
        memory_long="",
        active_plan={"plan_id": "p"},
        progress_state={"speaker_of_last_message": "seller"},
        world_state=huge_world,
        belief_state={"belief_buckets": {}},
        user_message="ok",
        state={"speaker_of_last_message": "seller"},
    )
    rendered = meta["advisor_input_prompt_rendered"]
    assert "world_full_json" in rendered
    assert len(rendered) < 30000


def test_advisor_prompt_spanish():
    assert "You are" not in ADVISOR_V2_SYSTEM_PROMPT


def test_advisor_limits_in_prompt():
    assert "max_questions" in ADVISOR_V2_SYSTEM_PROMPT
    assert "no revelar BATNA" in ADVISOR_V2_SYSTEM_PROMPT
    assert "pueden estar truncados" in ADVISOR_V2_SYSTEM_PROMPT
