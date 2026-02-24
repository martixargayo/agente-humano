from langchain_core.prompts import ChatPromptTemplate

from prompts import PLANNER_V2_SYSTEM_PROMPT, PLANNER_V2_USER_PROMPT
from negotiation.llm_planning_context import build_full_roleplay_profiles, build_world_digest
from negotiation.phase_policy_planner import (
    _build_policy_catalog_subset,
    _compact_policy_catalog_for_prompt,
    PLANNER_POLICY_CATALOG_MAX_CHARS,
    plan_phase_policy,
)
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


def test_planner_v2_prompt_template_renders_without_keyerror():
    prompt = ChatPromptTemplate.from_messages(
        [("system", PLANNER_V2_SYSTEM_PROMPT), ("user", PLANNER_V2_USER_PROMPT)]
    )

    messages = prompt.format_messages(
        full_profiles_block="",
        objective_summary="",
        judge_result_json="{}",
        advisor_recs_json="{}",
        policy_catalog_es_subset_json="{}",
        allowed_policy_ids_json="[]",
        phase_definitions_es="",
        memory_short="",
        memory_long="",
        world_digest_json="{}",
        world_full_json="{}",
        belief_digest_json="{}",
        belief_full_json="{}",
        policy_state_json="{}",
        phase_state_json="{}",
        active_plan_json="{}",
        progress_counters_json="{}",
        reusable_policy_id="",
    )

    assert messages


def test_plan_phase_policy_reports_prompt_format_stage_on_template_error(monkeypatch):
    broken_prompt = ChatPromptTemplate.from_messages(
        [("system", "broken {missing_var}"), ("user", "ok")]
    )
    monkeypatch.setattr("negotiation.phase_policy_planner._planner_v2_prompt", broken_prompt)

    phase_candidate, policy_decision, meta = plan_phase_policy(**_planner_inputs())

    assert phase_candidate["phase"] == "climate"
    assert policy_decision["policy_id"] == "safe_neutral"
    assert meta["planner_failed"] is True
    assert meta["planner_fallback_used"] is True
    assert meta["planner_error_stage"] == "prompt_format"


def test_planner_v2_prompt_labels_are_in_spanish():
    assert "B) BLOQUE_PERFILES_COMPLETOS" in PLANNER_V2_USER_PROMPT
    assert "F) ALLOWED_POLICY_IDS" in PLANNER_V2_USER_PROMPT
    assert "G) POLICY_CATALOG_ES_SUBSET (JSON)" in PLANNER_V2_USER_PROMPT
    assert "L) WORLD_COMPLETO_JSON" in PLANNER_V2_USER_PROMPT
    assert "N) BELIEF_COMPLETO_JSON" in PLANNER_V2_USER_PROMPT


def test_planner_v2_system_prompt_includes_anti_loop_initiative_rules():
    assert "INICIATIVA_Y_ANTI_LOOP" in PLANNER_V2_SYSTEM_PROMPT
    assert "SUFICIENTE PROVISIONAL" in PLANNER_V2_SYSTEM_PROMPT
    assert "Cambiar de táctica significa elegir UNA" in PLANNER_V2_SYSTEM_PROMPT
    assert "(D) Ancla u oferta condicional" in PLANNER_V2_SYSTEM_PROMPT
    assert "prueba de manejo" in PLANNER_V2_SYSTEM_PROMPT
    assert "climate/rapport" in PLANNER_V2_SYSTEM_PROMPT
    assert "BLOQUE_POLICY_SELECTION" in PLANNER_V2_SYSTEM_PROMPT
    assert "policy_catalog_es_subset" in PLANNER_V2_SYSTEM_PROMPT


def test_policy_catalog_subset_prompt_block_is_bounded_and_separated_from_allowed_ids():
    subset, subset_ids = _build_policy_catalog_subset(
        allowed_policy_ids=["safe_neutral", "set_process_rules", "meta_negotiation_reset"],
        planner_request="replan_policy",
        policy_state={},
        advisor_recs={"recommended_moves": [{"title": "usar proceso/decisión"}]},
        judge_result={"missing_signals": ["precio"]},
    )
    catalog_subset_json = _compact_policy_catalog_for_prompt(subset)
    assert subset_ids
    assert len(catalog_subset_json) <= PLANNER_POLICY_CATALOG_MAX_CHARS
    assert len(catalog_subset_json) < 9000
    assert "safe_neutral" in catalog_subset_json


def test_planner_v2_system_prompt_includes_anti_loop_initiative_rules():
    assert "INICIATIVA_Y_ANTI_LOOP" in PLANNER_V2_SYSTEM_PROMPT
    assert "SUFICIENTE PROVISIONAL" in PLANNER_V2_SYSTEM_PROMPT
    assert "Cambiar de táctica significa elegir UNA" in PLANNER_V2_SYSTEM_PROMPT
    assert "(D) Ancla u oferta condicional" in PLANNER_V2_SYSTEM_PROMPT
    assert "prueba de manejo" in PLANNER_V2_SYSTEM_PROMPT
    assert "climate/rapport" in PLANNER_V2_SYSTEM_PROMPT


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
