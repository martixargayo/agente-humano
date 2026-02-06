from __future__ import annotations

from negotiation.executor import render_executor
from negotiation.schemas import (
    default_belief_state,
    default_constraints_struct,
    default_persona_profile,
    default_scene_profile,
    default_style_contract,
    default_world_state,
)


class CaptureDeps:
    def __init__(self) -> None:
        self.messages = None

    def execute(self, messages):
        self.messages = messages
        return {
            "response_text": "ok",
            "asked_question": False,
            "requested_info_slots": [],
            "tone_used": "neutral",
            "followup_intent": None,
            "render_meta": {},
        }


def test_render_executor_prompt_includes_belief_summary():
    deps = CaptureDeps()
    state = {"belief_state": default_belief_state()}
    summary = {"micro_goal": "", "risk_posture": "", "why_short": "", "inputs_used": []}

    render_executor.render_executor_output(
        state,
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="universal",
        policy_id="safe_neutral",
        persona_profile=default_persona_profile(),
        scene_profile=default_scene_profile(),
        style_contract=default_style_contract(),
        constraints_struct=default_constraints_struct(),
        strategy_summary=summary,
        memory_block="",
        world_state=default_world_state(),
        user_message="hola",
    )

    prompt = deps.messages[1].content
    assert "belief_state_summary:" in prompt
    assert "interaction_health" in prompt
    assert "belief_summary_truncated:" in prompt


def test_summarize_belief_state_for_executor_truncates_large_payload():
    belief_state = default_belief_state()
    belief_state["negotiation"]["hypotheses"] = ["x" * 400 for _ in range(30)]
    belief_state["negotiation"]["stance"] = {"intent": "y" * 400, "risk": "z" * 400}

    summary = render_executor.summarize_belief_state_for_executor(belief_state)
    payload = render_executor._compact_json(summary["summary"])

    assert summary["truncated"] is True
    assert len(payload) <= render_executor._BELIEF_SUMMARY_MAX_CHARS


def test_summarize_belief_state_for_executor_handles_corrupt_input():
    summary = render_executor.summarize_belief_state_for_executor("bad")
    assert summary["summary"] == {}
    assert summary["truncated"] is False
