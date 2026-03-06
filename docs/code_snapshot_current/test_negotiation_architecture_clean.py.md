# File Snapshot

Original path:
`backend/tests/test_negotiation_architecture_clean.py`

Snapshot status:
`current`

Language / type:
`python`

```python
from __future__ import annotations

import ast
import inspect
import json
from types import SimpleNamespace

import pytest

import negociacion.flow_config as flow
from negociacion.canonical_state import CanonicalState, build_default_canonical_state
from negociacion.executor_node import ExecutorInput, ExecutorOutput
from negociacion.memory_node import DialogueMessage, MemoryEpisode, MemoryInput, MemoryOutput, MemoryWorking, TraceMeta
from negociacion.phase_classifier_node import PhaseClassifierInput, PhaseClassifierOutput
from negociacion.planner_node import PlannerInput, PlannerOutput
from negociacion.shared_types import NegotiationPhase, StructuredCallSource, ThreadMode
from state import SessionState


# --------------------------
# Helpers
# --------------------------

def _canonical() -> CanonicalState:
    return build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)


def _user_turn(text: str = "hola"):
    return flow._build_user_turn(text, "2025-01-01T00:00:00Z")


def _trace_meta() -> TraceMeta:
    return TraceMeta(turn_id="t1", prompt_version="memory_v3", schema_version="memory_input.v1", model_target="gpt-5-nano")


class _FakeConversation:
    def __init__(self, cid: str):
        self.id = cid


class _FakeConversations:
    def __init__(self):
        self.calls = 0

    def create(self):
        self.calls += 1
        return _FakeConversation(f"conv-{self.calls}")


class _FakeResponse:
    def __init__(self, rid: str, output_text: str = "", conversation_id: str | None = "conv-1", refusal: str | None = None):
        self.id = rid
        self.output_text = output_text
        self.refusal = refusal
        self.conversation = SimpleNamespace(id=conversation_id) if conversation_id else None


class _FakeResponses:
    def __init__(self, mode: str = "happy", phase: str = "clima_humano"):
        self.mode = mode
        self.phase = phase
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        schema_name = kwargs["text"]["format"]["name"]

        if self.mode == "planner_parse_error" and schema_name == "PlannerOutput":
            return _FakeResponse(f"r{idx}", output_text="{bad-json")
        if self.mode == "executor_refusal" and schema_name == "ExecutorOutput":
            return _FakeResponse(f"r{idx}", refusal="no puedo responder esto")

        payloads = {
            "MemoryOutput": {
                "schema_version": "memory.v1",
                "episodic_append": [
                    {"event_type": "important_fact", "summary": "quiere cerrar hoy", "turn_id": "turn-x"}
                ],
                "working_memory_new": {
                    "current_topic": "cierre",
                    "pending_question": "¿puede ser hoy?",
                    "last_turn_summary": "El usuario quiere cerrar hoy.",
                },
            },
            "PhaseClassifierOutput": {"current_phase": self.phase},
            "PlannerOutput": {
                "schema_version": "planner.v3",
                "status": "plan",
                "turn_goal": "avanzar con propuesta breve",
                "decision": "counter",
                "content_plan": {"must_include": ["propuesta concreta"], "must_avoid": ["inventar"]},
                "limits": {
                    "max_sentences": 3,
                    "max_questions": 1,
                    "allow_topic_shift": False,
                    "allow_personal_disclosure": False,
                },
                "memory_targets": ["episodic_0"],
                "done_criteria": ["propuesta_emitida"],
            },
            "ExecutorOutput": {
                "schema_version": "executor.v1",
                "status": "deliver",
                "spoken_text": "Perfecto, te propongo cerrar hoy con una condición clara.",
                "memory_used": ["episodic_0"],
                "refusal_reason": None,
            },
        }
        return _FakeResponse(f"r{idx}", output_text=json.dumps(payloads[schema_name]))


class _FakeClient:
    def __init__(self, mode: str = "happy", phase: str = "clima_humano"):
        self.conversations = _FakeConversations()
        self.responses = _FakeResponses(mode=mode, phase=phase)


# --------------------------
# A) Canonical state
# --------------------------

def test_canonical_state_has_exact_8_groups_in_fields_and_dump():
    c = _canonical()
    expected = {
        "session",
        "openai_thread",
        "persona",
        "memory_episodic",
        "memory_working",
        "negotiation_state",
        "planner_state",
        "trace",
    }
    assert set(CanonicalState.model_fields.keys()) == expected
    assert set(c.model_dump(mode="json").keys()) == expected


def test_canonical_state_exposes_no_legacy_shims_or_attrs():
    c = _canonical()
    for legacy in ["recent_messages", "session_settings", "memory_profile", "relationship", "safety", "voice", "plan"]:
        assert not hasattr(c, legacy)


# --------------------------
# B/C/D) Wiring + contracts + builders/messages
# --------------------------

def test_builders_wire_policy_phase_cards_limits_and_contract_shapes():
    c = _canonical()
    c.persona.policy.role_identity = "negociador senior"
    c.persona.expressive.max_sentences_default = 5
    c.planner_state.current_phase = NegotiationPhase.propuesta_creativa
    c.memory_episodic.append(flow.MemoryEpisodicItem(event_type="offer", event_summary="oferta inicial", turn_id="t-0"))

    recent = [DialogueMessage(role="user", text="quiero una propuesta"), DialogueMessage(role="assistant", text="te escucho")]
    user_turn = _user_turn("quiero una propuesta")
    trace = _trace_meta()

    mem_input = flow.build_memory_input(c, recent, user_turn, trace)
    phase_input = flow.build_phase_input(c, recent, user_turn, trace)
    planner_input = flow.build_planner_input(c, recent, user_turn, trace)

    planner_output = PlannerOutput.model_validate(
        {
            "schema_version": "planner.v3",
            "status": "plan",
            "turn_goal": "presentar propuesta",
            "decision": "counter",
            "content_plan": {"must_include": ["precio", "condiciones"], "must_avoid": ["promesas vacías"]},
            "limits": {
                "max_sentences": 2,
                "max_questions": 1,
                "allow_topic_shift": False,
                "allow_personal_disclosure": False,
            },
            "memory_targets": ["episodic_0"],
            "done_criteria": ["propuesta_entregada"],
        }
    )
    executor_input = flow.build_executor_input(c, recent, planner_output, user_turn, trace, max_recent_turns=2)

    assert isinstance(mem_input, MemoryInput)
    assert isinstance(phase_input, PhaseClassifierInput)
    assert isinstance(planner_input, PlannerInput)
    assert isinstance(executor_input, ExecutorInput)

    assert planner_input.persona_policy.role_identity == "negociador senior"
    assert planner_input.current_phase == NegotiationPhase.propuesta_creativa
    assert planner_input.phase_card.phase == NegotiationPhase.propuesta_creativa
    assert executor_input.persona_expressive.max_sentences_default == 5
    assert executor_input.phase_card.phase == NegotiationPhase.propuesta_creativa
    assert executor_input.response_limits.max_sentences == 2
    assert executor_input.response_limits.max_questions == 1
    assert executor_input.response_limits.allow_topic_shift is False

    for builder, prompt, payload in [
        (flow.build_memory_messages, "MEM PROMPT", mem_input),
        (flow.build_phase_classifier_messages_payload, "PHASE PROMPT", phase_input),
        (flow.build_planner_messages, "PLANNER PROMPT", planner_input),
        (flow.build_executor_messages, "EXEC PROMPT", executor_input),
    ]:
        messages = builder(prompt, payload)
        assert messages[0]["role"] == "developer"
        assert messages[0]["content"] == prompt
        assert messages[1]["role"] == "user"
        dynamic_json = messages[1]["content"]
        assert json.loads(dynamic_json)["trace_meta"]["turn_id"] == "t1"
        assert dynamic_json not in messages[0]["content"]


def test_state_apply_functions_update_only_expected_groups():
    c = _canonical()
    before = c.model_dump(mode="json")

    mem_out = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [{"event_type": "offer", "summary": "oferta 1", "turn_id": "t-1"}],
            "working_memory_new": {
                "current_topic": "precio",
                "pending_question": "¿incluye entrega?",
                "last_turn_summary": "Se propuso precio base.",
            },
        }
    )
    flow.apply_memory_output_to_state(c, mem_out)

    assert c.memory_episodic[-1].event_summary == "oferta 1"
    assert c.memory_working.current_topic == "precio"

    phase_out = PhaseClassifierOutput.model_validate({"current_phase": "concesiones_y_ajuste_final"})
    flow.apply_phase_classifier_output_to_state(c, phase_out)
    assert c.planner_state.previous_phase is None
    assert c.planner_state.current_phase == NegotiationPhase.concesiones_y_ajuste_final

    flow.apply_planner_output_to_state(
        c,
        PlannerOutput.model_validate(
            {
                "schema_version": "planner.v3",
                "status": "plan",
                "turn_goal": "cerrar términos",
                "decision": "close",
                "content_plan": {"must_include": ["términos"], "must_avoid": ["ambigüedad"]},
                "limits": {
                    "max_sentences": 3,
                    "max_questions": 0,
                    "allow_topic_shift": False,
                    "allow_personal_disclosure": False,
                },
                "memory_targets": [],
                "done_criteria": ["cierre_preparado"],
            }
        ),
    )
    assert c.planner_state.current_turn_goal == "cerrar términos"
    assert c.session.model_dump(mode="json") == before["session"]


def test_new_contracts_reject_legacy_fields_and_names():
    with pytest.raises(Exception):
        PlannerOutput.model_validate(
            {
                "schema_version": "planner.v3",
                "status": "plan",
                "turn_goal": "x",
                "decision": "none",
                "content_plan": {"must_include": [], "must_avoid": []},
                "limits": {
                    "max_sentences": 1,
                    "max_questions": 0,
                    "allow_topic_shift": False,
                    "allow_personal_disclosure": False,
                },
                "memory_targets": [],
                "done_criteria": ["ok"],
                "style_band": "short",
            }
        )

    planner_fields = set(PlannerOutput.model_fields.keys())
    for legacy in ["style_band", "conversation_act", "current_phase", "policy", "safety", "situation"]:
        assert legacy not in planner_fields

    executor_fields = set(ExecutorOutput.model_fields.keys())
    for legacy in ["tts", "conversation_act_realized"]:
        assert legacy not in executor_fields

    memory_names = {name for name, _ in inspect.getmembers(flow) if name.startswith("Memory")}
    for legacy in ["MemoryPatch", "profile_updates", "relationship_updates", "safety_updates"]:
        assert legacy not in memory_names


def test_builders_do_not_reference_legacy_canonical_properties():
    targets = [flow.build_memory_input, flow.build_phase_input, flow.build_planner_input, flow.build_executor_input]
    forbidden_attrs = {"recent_messages", "session_settings", "plan", "memory_profile", "relationship", "safety", "voice"}

    class _Visitor(ast.NodeVisitor):
        def __init__(self):
            self.found: set[str] = set()

        def visit_Attribute(self, node: ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "canonical_state" and node.attr in forbidden_attrs:
                self.found.add(node.attr)
            self.generic_visit(node)

    for fn in targets:
        tree = ast.parse(inspect.getsource(fn))
        visitor = _Visitor()
        visitor.visit(tree)
        assert visitor.found == set()


def test_shared_types_has_unique_enum_class_names():
    module = inspect.getsource(__import__("negociacion.shared_types", fromlist=["*"]))
    tree = ast.parse(module)
    class_names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    assert len(class_names) == len(set(class_names))


# --------------------------
# E/F) End-to-end and legacy absence in runtime
# --------------------------
@pytest.mark.parametrize(
    "user_message,phase",
    [
        ("hola, ¿cómo estás?", "clima_humano"),
        ("necesito entender condiciones y tiempos", "descubrimiento_y_comprension"),
        ("te ofrezco cerrar en dos pagos", "concesiones_y_ajuste_final"),
    ],
)
def test_end_to_end_turn_with_fake_client_updates_state_and_trace(monkeypatch, user_message: str, phase: str):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s1")

    fake_client = _FakeClient(mode="happy", phase=phase)
    monkeypatch.setattr(flow, "_build_client", lambda: fake_client)

    reply, updated = flow.run_negotiation_cognitive_turn(state, user_message, config)

    assert isinstance(reply, str) and reply
    world = updated.world_state[config.memory_key]
    assert world["planner_state"]["current_phase"] == phase
    assert world["memory_working"]["current_topic"] == "cierre"
    assert world["trace"]["last_node_statuses"].keys() == {"memory", "phase_classifier", "planner", "executor"}

    recent = updated.world_state[f"{config.memory_key}_recent_dialogue"]
    assert recent[-2]["role"] == "user" and "text" in recent[-2]
    assert recent[-1]["role"] == "assistant" and "text" in recent[-1]


def test_end_to_end_fallback_without_openai_client(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s2")
    monkeypatch.setattr(flow, "_build_client", lambda: None)

    reply, updated = flow.run_negotiation_cognitive_turn(state, "hola", config)

    assert reply
    trace = updated.world_state[config.memory_key]["trace"]
    assert set(trace["last_fallbacks"]) == {"memory", "phase_classifier", "planner", "executor"}


def test_end_to_end_parse_error_in_planner_uses_planner_fallback(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s3")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="planner_parse_error", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "propuesta", config)

    trace = updated.world_state[config.memory_key]["trace"]
    assert "planner" in trace["last_fallbacks"]


def test_end_to_end_refusal_in_executor_maps_to_refuse_status(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s4")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="executor_refusal", phase="propuesta_creativa"))

    reply, updated = flow.run_negotiation_cognitive_turn(state, "haz una propuesta", config)

    assert "No puedo ayudar" in reply
    trace = updated.world_state[config.memory_key]["trace"]
    assert "executor" in trace["last_fallbacks"]
    assert any("no puedo responder" in r for r in trace["last_refusals"])


def test_runtime_flow_does_not_depend_on_legacy_world_state_keys(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s5")
    state.world_state[config.memory_key] = {
        "session": {
            "session_id": "s5",
            "user_id": "u1",
            "avatar_id": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        },
        "openai_thread": {"thread_mode": "conversation", "conversation_id": None, "previous_response_id": None},
        "persona": {
            "policy": {
                "role_identity": "negociador",
                "negotiation_goal": "avanzar",
                "question_strategy": "minimal",
                "allow_topic_shift": False,
            },
            "expressive": {"tone": "neutral", "lexical_style": "plain", "max_sentences_default": 4},
        },
        "memory_episodic": [],
        "memory_working": {"current_topic": None, "pending_question": None, "last_turn_summary": None},
        "negotiation_state": {"last_offer_self": None, "last_offer_other": None, "blockers": []},
        "planner_state": {
            "current_phase": None,
            "previous_phase": None,
            "current_turn_goal": None,
            "topics_touched_current_phase": [],
            "topics_touched_previous_phases": [],
        },
        "trace": {"turn_id": None, "last_node_statuses": {}, "last_fallbacks": [], "last_refusals": []},
    }
    monkeypatch.setattr(flow, "_build_client", lambda: None)

    flow.run_negotiation_cognitive_turn(state, "mensaje", config)

    assert "recent_messages" not in state.world_state[config.memory_key]
    assert "session_settings" not in state.world_state[config.memory_key]
    assert "plan" not in state.world_state[config.memory_key]

```
