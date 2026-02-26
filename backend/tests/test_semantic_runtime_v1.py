import json

from negotiation.elementos.strategy_definitions import PlannerSemanticV1DecisionModel
from negotiation.nodes.world_node import world_judge_llm
from negotiation.phase_policy_planner import plan_phase_policy
from negotiation.progress_updater import update_progress_state
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.validation import normalize_world_buckets
from state import get_session_state
from negotiation.negotiation_graph import run_negotiation_agent


class _Raw:
    def __init__(self, content: str):
        self.content = content


class _JudgeLlmDummy:
    model = "dummy-semantic-judge"

    def invoke(self, _messages):
        return _Raw(
            json.dumps(
                {
                    "schema_version": "judge_semantic_v1",
                    "topic_alignment": "on_topic",
                    "reason_short": "Respuesta relacionada al tema.",
                    "semantic_ledger": {
                        "lo_que_ya_se_toco": ["Motivo de venta comentado."],
                        "lo_que_ya_pregunte": ["Pregunté por qué lo vendes."],
                        "lo_que_falta_pero_no_insistire": [],
                    },
                    "ledger_update_notes": "Actualización normal.",
                },
                ensure_ascii=False,
            )
        )


class _PlannerStructuredDummy:
    def invoke(self, _messages):
        return PlannerSemanticV1DecisionModel(
            schema_version="planner_semantic_v1",
            phase="descubrimiento_y_comprension",
            style="Calmo y práctico, sin insistir en lo ya tratado.",
            next_move_hint="Valida breve y pivota a precio/condiciones.",
            what_not_to_repeat=["No volver a preguntar por qué lo vende."],
        )


class _PlannerLlmDummy:
    model = "dummy-semantic-planner"

    def with_structured_output(self, _schema):
        return _PlannerStructuredDummy()


def test_world_judge_llm_parses_judge_semantic_v1(monkeypatch):
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _JudgeLlmDummy())
    progress_state = default_progress_state()
    out, _meta = world_judge_llm(
        user_message="Lo vendo porque ya no lo uso.",
        objective="Comprar Mustang",
        world_state=default_world_state(),
        recent_history="assistant: ¿por qué lo vendes?\nuser: porque ya no lo uso",
        turn_count=3,
        assistant_last_message="¿Por qué lo vendes?",
        progress_state=progress_state,
        state={},
    )
    assert out["schema_version"] == "judge_semantic_v1"
    assert out["topic_alignment"] in {"on_topic", "off_topic"}
    assert isinstance(out["semantic_ledger"]["lo_que_ya_pregunte"], list)


def test_progress_updater_persists_semantic_ledger_turn_to_turn():
    prev = default_progress_state()
    semantic_judge = {
        "schema_version": "judge_semantic_v1",
        "topic_alignment": "on_topic",
        "reason_short": "ok",
        "semantic_ledger": {
            "lo_que_ya_se_toco": ["Motivo de venta tratado."],
            "lo_que_ya_pregunte": ["Pregunté motivo de venta."],
            "lo_que_falta_pero_no_insistire": ["No sabe kilometraje exacto; no insistir."],
        },
        "ledger_update_notes": "ok",
    }
    out = update_progress_state(
        prev_progress=prev,
        policy_decision={"policy_id": "semantic_ledger", "reason": "", "micro_goal": "", "risk_posture": "low", "why_short": "", "inputs_used": []},
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=1,
        include_debug=False,
        semantic_judge=semantic_judge,
    )
    assert out["semantic_ledger"]["lo_que_ya_pregunte"] == ["Pregunté motivo de venta."]


def test_planner_semantic_model_validation_minimal():
    payload = PlannerSemanticV1DecisionModel(
        schema_version="planner_semantic_v1",
        phase="clima_humano",
        style="Breve y natural.",
        next_move_hint="Responder y dejar espacio.",
        what_not_to_repeat=[],
    )
    assert payload.schema_version == "planner_semantic_v1"


def test_e2e_motivo_venta_semantic_no_repeat(monkeypatch):
    monkeypatch.setattr("negotiation.phase_policy_planner.get_planner_llm", lambda: _PlannerLlmDummy())
    progress_state = default_progress_state()
    progress_state["semantic_ledger"] = {
        "lo_que_ya_se_toco": ["Motivo de venta tratado en el turno anterior."],
        "lo_que_ya_pregunte": ["Pregunté por qué lo vendes."],
        "lo_que_falta_pero_no_insistire": ["Motivo exacto no quedó claro; no insistir."],
    }

    _phase, _policy, meta = plan_phase_policy(
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        progress_state=progress_state,
        policy_state={},
        policy_plan_summary={},
        objective="Negociar compra Mustang",
        constraints="",
        recent_context="user: no lo sé exactamente\nassistant: ok",
        advisor_recs={},
        user_message="No lo sé, la verdad.",
        assistant_last_message="¿Por qué lo vendes?",
    )
    semantic = meta.get("planner_semantic_output") or {}
    assert semantic.get("schema_version") == "planner_semantic_v1"
    assert any("No volver a preguntar por qué lo vende." in x for x in semantic.get("what_not_to_repeat", []))


class _DepsCapturePlanner:
    def __init__(self):
        self.captured_assistant_last_message = None

    def plan_phase_policy(self, **kwargs):
        self.captured_assistant_last_message = kwargs.get("assistant_last_message")
        return (
            {
                "phase": "clima_humano",
                "confidence": 0.7,
                "reasons": [],
                "signals": [],
                "alternatives": [],
            },
            {"policy_id": "semantic_ledger", "reason": "", "micro_goal": "", "risk_posture": "low", "why_short": "", "inputs_used": []},
            {
                "planner_semantic_output": {
                    "schema_version": "planner_semantic_v1",
                    "phase": "clima_humano",
                    "style": "Breve.",
                    "next_move_hint": "Responder sin repetir.",
                    "what_not_to_repeat": [],
                }
            },
        )


def test_planner_node_uses_last_assistant_message_fallback():
    from negotiation.nodes.planner_node import phase_policy_planner_node

    deps = _DepsCapturePlanner()
    state = {
        "deps": deps,
        "objective": "",
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "world_diff": {},
        "belief_state": default_belief_state(),
        "advisor_recs": {},
        "semantic_judge": {},
        "short_memory": "",
        "long_memory": "",
        "user_message": "hola",
        "last_assistant_message": "ultimo mensaje asistente",
        "turn_count": 2,
    }
    out = phase_policy_planner_node(state)
    assert out["assistant_last_message"] == "ultimo mensaje asistente"
    assert deps.captured_assistant_last_message == "ultimo mensaje asistente"


def test_executor_prompt_uses_last_assistant_message_fallback():
    from negotiation.executor.render_executor import render_executor_output

    class _DepsExec:
        def __init__(self):
            self.messages = None

        def execute(self, messages):
            self.messages = messages
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )

    deps = _DepsExec()
    state = {
        "progress_state": default_progress_state(),
        "belief_state": default_belief_state(),
        "advisor_recs": {},
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": "clima_humano",
            "style": "Breve",
            "next_move_hint": "Validar y seguir",
            "what_not_to_repeat": [],
        },
        "last_assistant_message": "mensaje previo del asistente",
        "recent_history_text": "assistant: mensaje previo del asistente",
        "user_message": "ok",
    }
    render_executor_output(
        state,
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="universal",
        policy_id="semantic_ledger",
        persona_profile={},
        scene_profile={},
        style_contract={"max_words": 30, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="ok",
    )
    rendered = "\n".join(str(getattr(m, "content", "")) for m in (deps.messages or []))
    assert "assistant_last_message: mensaje previo del asistente" in rendered


def test_normalize_world_buckets_accepts_default_turn_kwarg():
    out = normalize_world_buckets({"interaction": {}, "notes": {}}, default_turn=123)
    assert isinstance(out, dict)
    assert set(out.keys()) == {"interaction", "notes"}


def test_executor_enforces_requested_slots_when_question_present():
    from negotiation.executor.render_executor import render_executor_output

    class _DepsExec:
        def execute(self, _messages):
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "¿Cuál es el precio final?",
                    "asked_question": True,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )

    state = {
        "progress_state": default_progress_state(),
        "belief_state": default_belief_state(),
        "advisor_recs": {},
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": "clima_humano",
            "style": "Breve",
            "next_move_hint": "Validar y seguir",
            "what_not_to_repeat": [],
        },
        "last_assistant_message": "mensaje previo",
        "recent_history_text": "assistant: mensaje previo",
        "user_message": "ok",
    }

    out = render_executor_output(
        state,
        deps=_DepsExec(),
        conversation_mode="negotiation",
        policy_pack_active="universal",
        policy_id="semantic_ledger",
        persona_profile={},
        scene_profile={},
        style_contract={"max_words": 30, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="ok",
    )
    assert out["asked_question"] is True
    assert out["requested_info_slots"] == ["precio_objetivo"]


class _RawMsg:
    def __init__(self, content: str):
        self.content = content


class _PlannerStructuredForRuntime:
    def invoke(self, _messages):
        return PlannerSemanticV1DecisionModel(
            schema_version="planner_semantic_v1",
            phase="clima_humano",
            style="Breve y natural.",
            next_move_hint="Responder y avanzar con naturalidad.",
            what_not_to_repeat=[],
        )


class _PlannerForRuntime:
    model = "dummy-semantic-planner"
    model_name = "dummy-semantic-planner"

    def with_structured_output(self, _schema):
        return _PlannerStructuredForRuntime()

    def invoke(self, _messages):
        return _RawMsg(
            json.dumps(
                {
                    "schema_version": "judge_semantic_v1",
                    "topic_alignment": "on_topic",
                    "reason_short": "ok",
                    "semantic_ledger": {
                        "lo_que_ya_se_toco": ["inicio"],
                        "lo_que_ya_pregunte": [],
                        "lo_que_falta_pero_no_insistire": [],
                    },
                    "ledger_update_notes": "ok",
                },
                ensure_ascii=False,
            )
        )


class _ExecutorForRuntime:
    model = "dummy-semantic-executor"
    model_name = "dummy-semantic-executor"

    def invoke(self, _messages):
        return _RawMsg(
            json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )
        )


def _run_semantic_turn_capture(monkeypatch):
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _PlannerForRuntime())
    monkeypatch.setattr("negotiation.phase_policy_planner.get_planner_llm", lambda: _PlannerForRuntime())
    monkeypatch.setattr("negotiation.state.deps.get_executor_llm", lambda: _ExecutorForRuntime())

    state = get_session_state("test_user_ctx", "test_session_ctx")
    run_negotiation_agent(state, "Hola, me interesa el Mustang")
    trace = state.debug_trace[-1]
    planner_prompt = ""
    executor_prompt = ""
    for call in (trace.get("trace_runtime") or {}).get("llm_calls", []):
        if call.get("name") == "planner_llm":
            planner_prompt = str(call.get("input_prompt_rendered") or "")
        if call.get("name") == "executor_llm":
            executor_prompt = str(call.get("input_prompt_rendered") or "")
    return planner_prompt, executor_prompt


def test_runtime_prompts_include_objective_profiles_phase_map_and_memory(monkeypatch):
    planner_prompt, executor_prompt = _run_semantic_turn_capture(monkeypatch)

    assert "PHASE CONTROL" in planner_prompt
    assert "allowed_next_phases" in planner_prompt
    assert "SEMANTIC_LEDGER" in planner_prompt
    assert "PHASES_RESUMEN" in planner_prompt

    assert "PHASE_CARD_EXTENDIDA" in executor_prompt
    assert "topic_selected:" in executor_prompt
    assert "SEMANTIC_LEDGER" in executor_prompt
    assert "phase_map_json" not in executor_prompt.lower()


def test_effective_ledger_is_shared_by_planner_and_executor(monkeypatch):
    planner_prompt, executor_prompt = _run_semantic_turn_capture(monkeypatch)
    assert 'lo_que_ya_se_toco' in planner_prompt
    assert 'lo_que_ya_se_toco' in executor_prompt
    assert '"inicio"' in planner_prompt
    assert '"inicio"' in executor_prompt


def test_trace_exposes_ledger_hash_observability(monkeypatch):
    monkeypatch.setattr("negotiation.nodes.world_node.get_planner_llm", lambda: _PlannerForRuntime())
    monkeypatch.setattr("negotiation.phase_policy_planner.get_planner_llm", lambda: _PlannerForRuntime())
    monkeypatch.setattr("negotiation.state.deps.get_executor_llm", lambda: _ExecutorForRuntime())

    state = get_session_state("test_user_hash", "test_session_hash")
    run_negotiation_agent(state, "Hola, me interesa el Mustang")
    trace = state.debug_trace[-1]
    assert isinstance(trace.get("planner_ledger_hash"), str)
    assert isinstance(trace.get("executor_ledger_hash"), str)
    assert isinstance(trace.get("effective_ledger_hash"), str)
    assert trace.get("planner_ledger_hash") == trace.get("executor_ledger_hash")
    assert trace.get("ledger_mismatch_detected") is False
