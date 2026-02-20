from langchain_core.prompts import ChatPromptTemplate

from prompts import PHASE_POLICY_SYSTEM_PROMPT, PHASE_POLICY_USER_PROMPT
from negotiation.phase_policy_planner import plan_phase_policy
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state


def _planner_inputs():
    return dict(
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        progress_state=default_progress_state(),
        policy_state={},
        policy_plan_summary={},
        objective="",
        constraints="",
        constraints_struct={},
        recent_context="",
        allowed_policy_ids=["safe_neutral"],
        advisor_recs={},
    )


def test_phase_policy_prompt_template_renders_without_keyerror():
    prompt = ChatPromptTemplate.from_messages(
        [("system", PHASE_POLICY_SYSTEM_PROMPT), ("user", PHASE_POLICY_USER_PROMPT)]
    )

    messages = prompt.format_messages(
        objective="",
        constraints="",
        recent_context="",
        phase_state="{}",
        active_plan="{}",
        policy_state="{}",
        allowed_policy_ids="[]",
        world_summary="{}",
        belief_summary="{}",
        advisor_recs="{}",
    )

    assert messages


def test_plan_phase_policy_reports_prompt_format_stage_on_template_error(monkeypatch):
    broken_prompt = ChatPromptTemplate.from_messages(
        [("system", "broken {missing_var}"), ("user", "ok")]
    )
    monkeypatch.setattr("negotiation.phase_policy_planner._planner_prompt", broken_prompt)

    phase_candidate, policy_decision, meta = plan_phase_policy(**_planner_inputs())

    assert phase_candidate["phase"] == "climate"
    assert policy_decision["policy_id"] == "safe_neutral"
    assert meta["planner_failed"] is True
    assert meta["planner_fallback_used"] is True
    assert meta["planner_error_stage"] == "prompt_format"


def test_phase_policy_prompt_is_minimal_without_policy_catalog_blobs():
    assert "{policy_catalog}" not in PHASE_POLICY_USER_PROMPT
    assert "{policy_catalog_with_phases}" not in PHASE_POLICY_USER_PROMPT
    assert "{world_diff}" not in PHASE_POLICY_USER_PROMPT
    assert "{belief_cues}" not in PHASE_POLICY_USER_PROMPT

def test_phase_policy_prompt_is_minimal_without_legacy_blobs():
    legacy_placeholders = [
        "{policy_catalog}",
        "{policy_catalog_with_phases}",
        "{world_diff}",
        "{belief_cues}",
        "{constraints_struct}",
        "{policy_plan_summary}",
    ]
    for placeholder in legacy_placeholders:
        assert placeholder not in PHASE_POLICY_USER_PROMPT

