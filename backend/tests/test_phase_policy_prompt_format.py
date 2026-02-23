from langchain_core.prompts import ChatPromptTemplate

from prompts import PHASE_POLICY_SYSTEM_PROMPT, PHASE_POLICY_USER_PROMPT, PLANNER_V2_USER_PROMPT
from negotiation.llm_planning_context import build_full_roleplay_profiles, build_world_digest
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


def test_planner_v2_prompt_labels_are_in_spanish():
    assert "B) BLOQUE_PERFILES_COMPLETOS" in PLANNER_V2_USER_PROMPT
    assert "K) WORLD_COMPLETO_JSON" in PLANNER_V2_USER_PROMPT
    assert "M) BELIEF_COMPLETO_JSON" in PLANNER_V2_USER_PROMPT


def test_build_full_roleplay_profiles_forces_carlos_when_scene_or_style_match():
    persona, scene, style, constraints = build_full_roleplay_profiles(
        {"render_state": {"scene_id": "mustang67_in_person_viewing"}}
    )
    assert persona["persona_id"] == "buyer_mustang67_v1"
    assert scene["scene_id"] == "mustang67_in_person_viewing"
    assert style["style_id"] == "psyplay_compact"
    assert constraints["max_questions"] == 1

    persona2, scene2, style2, _ = build_full_roleplay_profiles(
        {"render_state": {"style_id": "psyplay_compact"}}
    )
    assert persona2["persona_id"] == "buyer_mustang67_v1"
    assert scene2["scene_id"] == "mustang67_in_person_viewing"
    assert style2["style_id"] == "psyplay_compact"


def test_build_full_roleplay_profiles_forced_preset_is_not_mutated_across_calls():
    persona, _, _, _ = build_full_roleplay_profiles(
        {"render_state": {"style_id": "psyplay_compact"}}
    )
    persona["role_card"]["age"] = 99

    persona2, _, _, _ = build_full_roleplay_profiles(
        {"render_state": {"style_id": "psyplay_compact"}}
    )
    assert persona2["role_card"]["age"] == 26


def test_build_world_digest_includes_concessions_and_claims_keys():
    world_state = {
        "world_buckets": {
            "offers": [{"v": "o"}],
            "concessions": [{"v": "c"}],
            "claims": [{"v": "k"}],
            "constraints": [{"v": "x"}],
        }
    }
    digest = build_world_digest(world_state, {"changed": True})
    assert "concessions" in digest["top"]
    assert "claims" in digest["top"]
