from negotiation.elementos.render.carlos_buyer_preset import (
    CARLOS_CONSTRAINTS_STRUCT,
    CARLOS_PERSONA_PROFILE,
    CARLOS_SCENE_PROFILE,
    CARLOS_STYLE_CONTRACT,
)
from negotiation.extractors.belief_extractor_v1 import (
    BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT,
    extract_belief_state_llm_v1,
)
from negotiation.extractors.world_extractor_v4 import (
    WORLD_EXTRACTOR_V4_SYSTEM_PROMPT,
    extract_world_patch_llm_v4,
)
from negotiation.llm_background import build_background_public_block
from negotiation.schemas import default_belief_state, default_world_state


class _WorldDeps:
    def __init__(self):
        self.messages = []

    class _LLM:
        def __init__(self, outer):
            self.outer = outer

        def invoke(self, messages):
            self.outer.messages = messages
            return (
                '{"schema_version":"world_extractor_v4","world_buckets_patch":'
                '{"offers":[],"concessions":[{"text":"El vendedor indica que está dispuesto a hacer concesiones por dinero hoy",'
                '"confidence":0.87,"raw_text":"estoy dispuesto a hacer concesiones a cambio de dinero hoy","source_turn":1}],'
                '"constraints":[],"interests":[],"claims":[],"requests":[],"context":[{"text":"hoy",'
                '"confidence":0.72,"raw_text":"hoy","source_turn":1}]},"meta":{}}'
            )

    @property
    def llm(self):
        return self._LLM(self)


class _BeliefDeps:
    def __init__(self):
        self.messages = []

    def execute(self, messages):
        self.messages = messages
        return (
            '{"schema_version":"v3","belief_buckets":{"hypotheses":[{"text":"El vendedor podría priorizar liquidez inmediata",'
            '"confidence":0.76,"status":"new"}],"strategy_notes":[{"text":"Conviene validar condiciones hoy antes de ceder precio",'
            '"confidence":0.71,"status":"new"}],"risk_flags":[],"watch_items":[]},'
            '"planner_signals":{"interaction_health":"stable","conflict_risk":0.2,"recommended_move":"hold","recovery_mode":false}}'
        )


def _background_block(speaker: str = "seller") -> str:
    return build_background_public_block(
        CARLOS_PERSONA_PROFILE,
        CARLOS_SCENE_PROFILE,
        CARLOS_STYLE_CONTRACT,
        CARLOS_CONSTRAINTS_STRUCT,
        language="es",
        task_type="negotiation",
        domain="mustang67_car_purchase",
        participants={"buyer": "Carlos", "seller": "Don Joaquín"},
        speaker_of_user_message=speaker,
    )


def test_prompts_system_en_castellano():
    assert "You are" not in WORLD_EXTRACTOR_V4_SYSTEM_PROMPT
    assert "You are" not in BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT
    assert "PersonaProfile/SceneProfile/StyleContract/ConstraintsStruct" not in WORLD_EXTRACTOR_V4_SYSTEM_PROMPT
    assert "PersonaProfile/SceneProfile/StyleContract/ConstraintsStruct" not in BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT
    assert "BACKGROUND_CONTEXT" in WORLD_EXTRACTOR_V4_SYSTEM_PROMPT
    assert "CONSTRAINTS_PUBLIC" in WORLD_EXTRACTOR_V4_SYSTEM_PROMPT
    assert "BACKGROUND_CONTEXT" in BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT
    assert "CONSTRAINTS_PUBLIC" in BELIEF_EXTRACTOR_V1_SYSTEM_PROMPT


def test_background_public_block_is_sanitized_and_reusable():
    block = _background_block("seller")
    assert "BACKGROUND_CONTEXT:" in block
    assert "speaker_of_user_message: seller" in block
    assert "PERSONA_PUBLIC:" in block
    assert "SCENE_PUBLIC:" in block
    assert "STYLE_PUBLIC:" in block
    assert "CONSTRAINTS_PUBLIC:" in block
    assert "8000" not in block
    assert "BATNA: buy same model" not in block


def test_world_extractor_seller_attribution_spanish_and_no_persona_leak():
    deps = _WorldDeps()
    patch, meta = extract_world_patch_llm_v4(
        deps,
        user_message="estoy dispuesto a hacer concesiones a cambio de dinero hoy",
        prev_world_state=default_world_state(),
        belief_state=default_belief_state(),
        conversation_mode="negotiation",
        turn_idx=1,
        speaker_of_user_message="seller",
        persona_profile=CARLOS_PERSONA_PROFILE,
        scene_profile=CARLOS_SCENE_PROFILE,
        style_contract=CARLOS_STYLE_CONTRACT,
        constraints_struct=CARLOS_CONSTRAINTS_STRUCT,
        background_block_public=_background_block("seller"),
    )

    texts = [item["text"] for items in patch.values() for item in items]
    assert any("vendedor" in txt.lower() or "don joaquín" in txt.lower() for txt in texts)
    assert all("willing to" not in txt.lower() for txt in texts)
    assert all("8000" not in txt for txt in texts)

    user_prompt = deps.messages[1]["content"]
    assert "BACKGROUND_CONTEXT:" in user_prompt
    assert "MENSAJE ACTUAL:" in user_prompt
    assert "MENSAJE ACTUAL expresa intercambio condicional o implícito" in user_prompt
    assert "speaker_of_user_message: seller" in user_prompt
    assert "persona_profile:" not in user_prompt
    assert "scene_profile:" not in user_prompt
    assert "style_contract:" not in user_prompt
    assert "constraints_struct:" not in user_prompt
    assert "8000" not in user_prompt
    assert "BACKGROUND_CONTEXT:" in meta["extractor_input_prompt_rendered"]
    assert "persona_profile:" not in meta["extractor_input_prompt_rendered"]
    assert meta["extractor_output_payload_raw"]["schema_version"] == "world_extractor_v4"


def test_belief_extractor_seller_perspective_spanish_and_no_persona_leak():
    deps = _BeliefDeps()
    world = default_world_state()
    world["world_buckets"]["claims"] = [
        {
            "text": "El vendedor indica que necesita cerrar hoy",
            "confidence": 0.81,
            "raw_text": "necesito cerrar hoy",
            "source_turn": 2,
        }
    ]

    belief_state, meta = extract_belief_state_llm_v1(
        deps=deps,
        user_message="necesito cerrar hoy",
        world_state=world,
        prev_belief_state=default_belief_state(),
        turn_idx=2,
        speaker_of_user_message="seller",
        persona_profile=CARLOS_PERSONA_PROFILE,
        scene_profile=CARLOS_SCENE_PROFILE,
        style_contract=CARLOS_STYLE_CONTRACT,
        constraints_struct=CARLOS_CONSTRAINTS_STRUCT,
        background_block_public=_background_block("seller"),
    )

    hyp_texts = [item["text"] for item in belief_state["belief_buckets"]["hypotheses"]]
    strategy_texts = [item["text"] for item in belief_state["belief_buckets"]["strategy_notes"]]
    assert all("user is" not in txt.lower() for txt in hyp_texts)
    assert all("willing to" not in txt.lower() for txt in (hyp_texts + strategy_texts))
    assert all("8000" not in txt for txt in (hyp_texts + strategy_texts))
    assert any("vendedor" in txt.lower() for txt in hyp_texts)

    user_prompt = deps.messages[1]["content"]
    assert "BACKGROUND_CONTEXT:" in user_prompt
    assert "MENSAJE_ACTUAL:" in user_prompt
    assert "speaker_of_user_message: seller" in user_prompt
    assert "persona_profile:" not in user_prompt
    assert "scene_profile:" not in user_prompt
    assert "8000" not in user_prompt
    assert "BACKGROUND_CONTEXT:" in meta["belief_input_prompt_rendered"]
    assert "persona_profile:" not in meta["belief_input_prompt_rendered"]
    assert meta["belief_output_payload_raw"]["schema_version"] == "v3"


class _WorldDepsEmptyPatch:
    def __init__(self):
        self.messages = []

    class _LLM:
        def __init__(self, outer):
            self.outer = outer

        def invoke(self, messages):
            self.outer.messages = messages
            return (
                '{"schema_version":"world_extractor_v4","world_buckets_patch":'
                '{"offers":[],"concessions":[],"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},'
                '"meta":{"negotiation_signal_detected":true,"extraction_quality":"high"}}'
            )

    @property
    def llm(self):
        return self._LLM(self)


def test_world_extractor_postprocess_keeps_empty_requests_without_llm_item():
    deps = _WorldDepsEmptyPatch()
    patch, meta = extract_world_patch_llm_v4(
        deps,
        user_message="Yo no tengo nada que decir, ¿qué me ofreces?",
        prev_world_state=default_world_state(),
        belief_state=default_belief_state(),
        conversation_mode="negotiation",
        turn_idx=5,
        speaker_of_user_message="seller",
        persona_profile=CARLOS_PERSONA_PROFILE,
        scene_profile=CARLOS_SCENE_PROFILE,
        style_contract=CARLOS_STYLE_CONTRACT,
        constraints_struct=CARLOS_CONSTRAINTS_STRUCT,
        background_block_public=_background_block("seller"),
    )

    assert patch["requests"] == []
    assert meta.get("postprocess_reason_codes") in (None, [])
