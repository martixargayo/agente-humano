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
import time
from types import SimpleNamespace

import pytest

import negociacion.flow_config as flow
from negociacion.canonical_state import CanonicalState, build_default_canonical_state
from negociacion.executor_node import ExecutorInput, ExecutorOutput
from negociacion.memory_node import DialogueMessage, MemoryInput, MemoryOutput, TraceMeta
from negociacion.phase_classifier_node import PhaseClassifierInput, PhaseClassifierOutput
from negociacion.planner_node import PlannerInput, PlannerOutput
from negociacion.shared_types import NegotiationPhase, ThreadMode
from state import SessionState


def _canonical(mode: ThreadMode = ThreadMode.conversation) -> CanonicalState:
    return build_default_canonical_state(session_id="s1", user_id="u1", thread_mode=mode)


def _user_turn(text: str = "hola"):
    return flow._build_user_turn(text, "2025-01-01T00:00:00Z")


def _trace_meta() -> TraceMeta:
    return TraceMeta(turn_id="t1", prompt_version="memory_v3", schema_version="memory_input.v1", model_target="gpt-5-nano")


class _FakeConversation:
    def __init__(self, cid: str):
        self.id = cid


class _FakeConversations:
    def __init__(self):
        self.created = 0

    def create(self):
        self.created += 1
        return _FakeConversation(f"conv-{self.created}")


class _FakeResponse:
    def __init__(self, rid: str, output_text: str = "", conversation_id: str | None = "conv-1", refusal: str | None = None):
        self.id = rid
        self.output_text = output_text
        self.refusal = refusal
        self.conversation = SimpleNamespace(id=conversation_id) if conversation_id else None


class _RecordingResponses:
    def __init__(self, mode: str = "happy", phase: str = "clima_humano", delay_s: float = 0.0):
        self.mode = mode
        self.phase = phase
        self.delay_s = delay_s
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        schema_name = kwargs["text"]["format"]["name"]

        if self.delay_s and schema_name in {"MemoryOutput", "PhaseClassifierOutput"}:
            time.sleep(self.delay_s)

        if self.mode == "planner_parse_error" and schema_name == "PlannerOutput":
            return _FakeResponse(f"r{idx}", output_text="{bad-json")
        if self.mode == "executor_refusal" and schema_name == "ExecutorOutput":
            return _FakeResponse(f"r{idx}", refusal="no puedo responder esto")

        executor_spoken_text = "Perfecto, te propongo cerrar hoy con una condición clara."
        executor_refusal_reason = None
        executor_status = "deliver"
        if self.mode == "executor_guardrail_rewrite":
            executor_spoken_text = "Pásame tu DNI y te garantizo 100% el resultado."  # triggers optional output guardrail
        if self.mode == "executor_domain_guardrail":
            executor_spoken_text = "Te doy una pauta médica concreta."
        if self.mode == "executor_final_refusal_reason":
            executor_status = "refuse"
            executor_spoken_text = "No puedo continuar con esto."
            executor_refusal_reason = "policy_refusal"

        payloads = {
            "MemoryOutput": {
                "schema_version": "memory.v1",
                "episodic_append": [{"event_type": "important_fact", "summary": "quiere cerrar hoy", "turn_id": "turn-x"}],
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
                "status": executor_status,
                "spoken_text": executor_spoken_text,
                "memory_used": ["episodic_0"],
                "refusal_reason": executor_refusal_reason,
            },
        }
        return _FakeResponse(f"r{idx}", output_text=json.dumps(payloads[schema_name]), conversation_id="conv-1")


class _FakeClient:
    def __init__(self, mode: str = "happy", phase: str = "clima_humano", delay_s: float = 0.0):
        self.conversations = _FakeConversations()
        self.responses = _RecordingResponses(mode=mode, phase=phase, delay_s=delay_s)


def _make_state_with_mode(mode: ThreadMode, previous_response_id: str | None = None) -> SessionState:
    state = SessionState(user_id="u1", session_id="s1")
    canonical = build_default_canonical_state(session_id="s1", user_id="u1", thread_mode=mode)
    canonical.openai_thread.previous_response_id = previous_response_id
    state.world_state["negotiation_canonical"] = canonical.model_dump(mode="json")
    return state


# Canonical + contracts

def test_canonical_state_has_exact_8_groups_and_no_legacy_attrs():
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
    for legacy in ["recent_messages", "session_settings", "memory_profile", "relationship", "safety", "voice", "plan"]:
        assert not hasattr(c, legacy)


def test_builders_wiring_and_message_contracts():
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
            "content_plan": {"must_include": ["precio"], "must_avoid": ["promesas vacías"]},
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
    assert planner_input.phase_card.phase == NegotiationPhase.propuesta_creativa
    assert executor_input.persona_expressive.max_sentences_default == 5
    assert executor_input.response_limits.max_sentences == 2

    for builder, prompt, payload in [
        (flow.build_memory_messages, "MEM PROMPT", mem_input),
        (flow.build_phase_classifier_messages_payload, "PHASE PROMPT", phase_input),
        (flow.build_planner_messages, "PLANNER PROMPT", planner_input),
        (flow.build_executor_messages, "EXEC PROMPT", executor_input),
    ]:
        messages = builder(prompt, payload)
        assert messages[0] == {"role": "developer", "content": prompt}
        assert messages[1]["role"] == "user"
        assert "\"trace_meta\"" in messages[1]["content"]
        assert messages[1]["content"] not in messages[0]["content"]


def test_state_apply_functions_update_expected_groups():
    c = _canonical()
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
    flow.apply_phase_classifier_output_to_state(c, PhaseClassifierOutput(current_phase=NegotiationPhase.concesiones_y_ajuste_final))
    assert c.memory_episodic[-1].event_summary == "oferta 1"
    assert c.memory_working.current_topic == "precio"
    assert c.planner_state.current_phase == NegotiationPhase.concesiones_y_ajuste_final


def test_contracts_and_builders_reject_legacy_surfaces():
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

    for legacy in ["style_band", "conversation_act", "current_phase", "policy", "safety", "situation"]:
        assert legacy not in PlannerOutput.model_fields
    for legacy in ["tts", "conversation_act_realized"]:
        assert legacy not in ExecutorOutput.model_fields

    class _Visitor(ast.NodeVisitor):
        def __init__(self):
            self.found: set[str] = set()

        def visit_Attribute(self, node: ast.Attribute):
            forbidden = {"recent_messages", "session_settings", "plan", "memory_profile", "relationship", "safety", "voice"}
            if isinstance(node.value, ast.Name) and node.value.id == "canonical_state" and node.attr in forbidden:
                self.found.add(node.attr)
            self.generic_visit(node)

    for fn in [flow.build_memory_input, flow.build_phase_input, flow.build_planner_input, flow.build_executor_input]:
        tree = ast.parse(inspect.getsource(fn))
        v = _Visitor()
        v.visit(tree)
        assert v.found == set()


# load_state fallback

def test_load_state_fallback_keeps_session_identity_on_corruption():
    repo = flow.StateRepository(memory_key="negotiation_canonical")
    state = SessionState(user_id="u-real", session_id="s-real")
    state.world_state["negotiation_canonical"] = {"broken": True}

    canonical = repo.load_state(state)

    assert canonical.session.session_id == "s-real"
    assert canonical.session.user_id == "u-real"
    assert isinstance(canonical, CanonicalState)


def test_load_state_fallback_uses_pending_only_when_session_identity_missing():
    fallback = flow._default_canonical_state(session_state=None)
    assert fallback.session.session_id == "pending_session"


# ensure_openai_thread

def test_ensure_openai_thread_keeps_stable_mode_for_valid_state(monkeypatch):
    c = _canonical(mode=ThreadMode.previous_response_id)
    c.openai_thread.previous_response_id = "parent-1"

    thread = flow.ensure_openai_thread(client=None, canonical_state=c, mode_default=ThreadMode.conversation)

    assert thread.thread_mode == ThreadMode.previous_response_id
    assert thread.previous_response_id == "parent-1"


def test_ensure_openai_thread_bootstraps_conversation_if_needed():
    c = _canonical(mode=ThreadMode.conversation)
    client = _FakeClient()

    thread = flow.ensure_openai_thread(client=client, canonical_state=c, mode_default=ThreadMode.conversation)

    assert thread.thread_mode == ThreadMode.conversation
    assert thread.conversation_id == "conv-1"


# shared_types hygiene

def test_shared_types_contains_only_current_enum_surface():
    import negociacion.shared_types as shared

    module = inspect.getsource(shared)
    tree = ast.parse(module)
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == len(set(class_names))

    removed = {
        "PlannerStatus",
        "ExecutorStatus",
        "ConversationAct",
        "LengthBand",
        "DirectnessLevel",
        "InitiativeLevel",
        "EmotionalIntensity",
        "SafetyRiskLevel",
    }
    assert removed.isdisjoint(set(class_names))


# end-to-end + threading modes + refusals

def test_e2e_happy_path(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-happy")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="happy", phase="clima_humano"))

    reply, updated = flow.run_negotiation_cognitive_turn(state, "hola", config)

    assert reply
    trace = updated.world_state[config.memory_key]["trace"]
    assert trace["last_refusals"] == []


def test_e2e_fallback_without_openai_client(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-fallback")
    monkeypatch.setattr(flow, "_build_client", lambda: None)

    _, updated = flow.run_negotiation_cognitive_turn(state, "hola", config)

    trace = updated.world_state[config.memory_key]["trace"]
    assert set(trace["last_fallbacks"]) == {"memory", "phase_classifier", "planner", "executor"}


def test_e2e_parse_error_path(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-parse")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="planner_parse_error", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "propuesta", config)

    assert "planner" in updated.world_state[config.memory_key]["trace"]["last_fallbacks"]


def test_e2e_refusal_path_model_refusal_deduped_in_trace(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-refusal")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="executor_refusal", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "haz una propuesta", config)

    refusals = updated.world_state[config.memory_key]["trace"]["last_refusals"]
    assert refusals.count("no puedo responder esto") == 1


def test_trace_last_refusals_includes_guardrail_rewrite_reason(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-guardrail-rewrite")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="executor_guardrail_rewrite", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "haz una propuesta", config)

    refusals = updated.world_state[config.memory_key]["trace"]["last_refusals"]
    assert "safety_rewrite_required" in refusals
    assert "optional_output_guardrail" in refusals


def test_trace_last_refusals_includes_executor_final_refusal_reason(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-final-reason")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="executor_final_refusal_reason", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "haz una propuesta", config)

    refusals = updated.world_state[config.memory_key]["trace"]["last_refusals"]
    assert "policy_refusal" in refusals


def test_trace_last_refusals_includes_domain_guardrail(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = SessionState(user_id="u1", session_id="s-domain")
    monkeypatch.setattr(flow, "_build_client", lambda: _FakeClient(mode="executor_domain_guardrail", phase="propuesta_creativa"))

    _, updated = flow.run_negotiation_cognitive_turn(state, "tengo un síntoma y necesito diagnóstico", config)

    refusals = updated.world_state[config.memory_key]["trace"]["last_refusals"]
    assert "domain_restriction:medical" in refusals
    assert "optional_domain_guardrail" in refusals


def test_threading_conversation_keeps_parallelizable_memory_and_phase(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    state = _make_state_with_mode(ThreadMode.conversation)
    fake = _FakeClient(mode="happy", phase="clima_humano", delay_s=0.18)
    monkeypatch.setattr(flow, "_build_client", lambda: fake)

    start = time.perf_counter()
    flow.run_negotiation_cognitive_turn(state, "hola", config)
    elapsed = time.perf_counter() - start

    # Si fueran secuenciales estrictos serían ~0.36s solo memory+phase; con paralelo debe quedar claramente por debajo.
    assert elapsed < 0.32


def test_threading_previous_response_id_forces_sequential_chain_and_context(monkeypatch):
    config = flow.build_negotiation_pipeline_config()
    config.thread_mode_default = ThreadMode.previous_response_id
    state = _make_state_with_mode(ThreadMode.previous_response_id, previous_response_id="seed-parent")
    fake = _FakeClient(mode="happy", phase="descubrimiento_y_comprension", delay_s=0.08)
    monkeypatch.setattr(flow, "_build_client", lambda: fake)

    start = time.perf_counter()
    flow.run_negotiation_cognitive_turn(state, "hola", config)
    elapsed = time.perf_counter() - start

    calls = fake.responses.calls
    by_schema = [(c["text"]["format"]["name"], c.get("previous_response_id"), c.get("conversation")) for c in calls]

    assert [name for name, _, _ in by_schema] == ["MemoryOutput", "PhaseClassifierOutput", "PlannerOutput", "ExecutorOutput"]
    assert by_schema[0][1] == "seed-parent"
    assert by_schema[1][1] == "r1"
    assert by_schema[2][1] == "r2"
    assert by_schema[3][1] == "r3"
    assert all(conv is None for _, _, conv in by_schema)
    assert state.world_state[config.memory_key]["openai_thread"]["previous_response_id"] == "r4"

    # Dos llamadas con 0.08s en cadena deben ser >=0.16s.
    assert elapsed >= 0.16

```
