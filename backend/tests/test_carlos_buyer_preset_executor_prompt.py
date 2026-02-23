import copy
import json

from negotiation.elementos.render.carlos_buyer_preset import (
    CARLOS_CONSTRAINTS_STRUCT,
    CARLOS_PERSONA_PROFILE,
    CARLOS_SCENE_PROFILE,
    CARLOS_STYLE_CONTRACT,
)
from negotiation.elementos.render.constraints_builder import build_constraints_struct
from negotiation.executor import render_executor_output


class _Deps:
    def __init__(self):
        self.messages = None

    def execute(self, messages):
        self.messages = messages
        return '{"response_text":"ok","asked_question":false,"requested_info_slots":[],"tone_used":"neutral","followup_intent":null,"render_meta":{}}'


def test_carlos_preset_prompt_and_constraints_exact():
    deps = _Deps()
    persona = copy.deepcopy(CARLOS_PERSONA_PROFILE)
    scene = copy.deepcopy(CARLOS_SCENE_PROFILE)
    style = copy.deepcopy(CARLOS_STYLE_CONTRACT)
    constraints = copy.deepcopy(CARLOS_CONSTRAINTS_STRUCT)

    result = render_executor_output(
        state={"belief_state": {}},
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="negotiation",
        policy_id="safe_neutral",
        persona_profile=persona,
        scene_profile=scene,
        style_contract=style,
        constraints_struct=constraints,
        strategy_summary={},
        memory_block="",
        world_state={},
        user_message="Hola",
    )

    assert result["response_text"] == "ok"

    prompt = deps.messages[1].content
    assert "BLOQUE_PERFILES_COMPLETOS:" in prompt
    assert f"PERSONA_PROFILE_JSON: {json.dumps(CARLOS_PERSONA_PROFILE, ensure_ascii=False)}" in prompt
    assert f"ESCENA_PROFILE_JSON: {json.dumps(CARLOS_SCENE_PROFILE, ensure_ascii=False)}" in prompt
    assert f"STYLE_CONTRACT_JSON: {json.dumps(CARLOS_STYLE_CONTRACT, ensure_ascii=False)}" in prompt
    assert f"CONSTRAINTS_STRUCT_JSON: {json.dumps(CARLOS_CONSTRAINTS_STRUCT, ensure_ascii=False)}" in prompt
    assert "PERSONA PROFILE (fixed):" not in prompt
    assert "SCENE PROFILE (fixed):" not in prompt

    assert persona == CARLOS_PERSONA_PROFILE
    assert scene == CARLOS_SCENE_PROFILE
    assert style == CARLOS_STYLE_CONTRACT
    assert constraints == CARLOS_CONSTRAINTS_STRUCT

    built_constraints = build_constraints_struct(
        world={},
        belief={},
        progress={"conversation_mode": "negotiation"},
        decision={},
        persona=CARLOS_PERSONA_PROFILE,
        scene=CARLOS_SCENE_PROFILE,
        style=CARLOS_STYLE_CONTRACT,
    )
    assert built_constraints == CARLOS_CONSTRAINTS_STRUCT
    assert "markdown" in built_constraints["forbid_formats"]
    assert built_constraints["max_questions"] == 1
