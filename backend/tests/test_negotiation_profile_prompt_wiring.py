import json

from negotiation.negotiation_profiles import (
    NEGOTIATION_PROFILE_PRIVATE_EXECUTOR_V1,
    NEGOTIATION_PROFILE_PRIVATE_PLANNER_V1,
)
from prompts import PLANNER_SEMANTIC_V1_USER_PROMPT
from negotiation.elementos.render.executor_prompts import (
    EXECUTOR_FINALIZER_V1_USER_PROMPT,
    EXECUTOR_V2_USER_PROMPT,
)


def test_planner_negotiation_profile_placeholder_resolves():
    rendered = PLANNER_SEMANTIC_V1_USER_PROMPT.format(
        speaker="seller",
        user_message="hola",
        assistant_last_message="ok",
        style_id="psyplay_compact",
        max_words=30,
        max_questions=1,
        prev_phase="clima_humano",
        allowed_next_phases_json=json.dumps(["clima_humano"], ensure_ascii=False),
        lo_que_ya_se_toco_json="[]",
        lo_que_ya_pregunte_json="[]",
        lo_que_falta_pero_no_insistire_json="[]",
        recent_history_compact="",
        objective_summary_compact="obj",
        negotiation_profile_private_planner=str(NEGOTIATION_PROFILE_PRIVATE_PLANNER_V1 or ""),
    )
    assert "{negotiation_profile_private_planner}" not in rendered


def test_executor_and_finalizer_negotiation_profile_placeholder_resolves():
    executor_rendered = EXECUTOR_V2_USER_PROMPT.format(
        speaker="seller",
        user_message="hola",
        last_seller_utterance="hola",
        assistant_last_message="ok",
        style_id="psyplay_compact",
        max_words=40,
        max_questions=1,
        prev_phase="clima_humano",
        planner_semantic_output_json="{}",
        phase="clima_humano",
        phase_do_text="do",
        phase_tecnicas_text="tecnicas",
        phase_evitar_text="evitar",
        phase_question_policy="policy",
        phase_topics_json="[]",
        topic_selected="topic",
        profile_card_compact_text="profile",
        scene_card_compact_text="scene",
        lo_que_ya_se_toco_json="[]",
        lo_que_ya_pregunte_json="[]",
        lo_que_falta_pero_no_insistire_json="[]",
        recent_history_compact="",
        memory_long_compact="",
        negotiation_profile_private_executor=str(NEGOTIATION_PROFILE_PRIVATE_EXECUTOR_V1 or ""),
        retry_hint="",
    )
    assert "{negotiation_profile_private_executor}" not in executor_rendered

    finalizer_rendered = EXECUTOR_FINALIZER_V1_USER_PROMPT.format(
        target_words=26,
        max_words=30,
        max_questions=1,
        prev_turn_asked_question="false",
        last_seller_utterance="hola",
        user_message="hola",
        assistant_last_message="ok",
        phase="clima_humano",
        prev_phase="clima_humano",
        topic_selected="topic",
        objective_delta="reduce_risk",
        tactic="frame",
        planner_semantic_output_json="{}",
        semantic_ledger_json="{}",
        memory_short_compact="",
        memory_long_compact="",
        negotiation_profile_private_executor=str(NEGOTIATION_PROFILE_PRIVATE_EXECUTOR_V1 or ""),
        executor_draft_json="{}",
    )
    assert "{negotiation_profile_private_executor}" not in finalizer_rendered
