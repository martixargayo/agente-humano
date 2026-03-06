from types import SimpleNamespace

import negociacion.flow_config as arch
from negociacion.cognitive_architecture import (
    ConversationAct,
    ExecutorOutput,
    ExecutorStatus,
    MemoryEpisode,
    MemoryPatch,
    PlannerOutput,
    PlannerStatus,
    StructuredCallSource,
    ThreadMode,
    TraceMeta,
    UserTurn,
    apply_memory_patch,
    build_executor_input,
    build_planner_input,
    check_openai_sdk_compatibility,
    run_negotiation_cognitive_turn,
)
from negociacion.flow_config import build_negotiation_pipeline_config
from state import SessionState


class FakeConversation:
    def __init__(self, cid: str):
        self.id = cid


class FakeResponse:
    def __init__(self, response_id: str, output_text: str = "", conversation_id: str | None = None, refusal: str | None = None):
        self.id = response_id
        self.output_text = output_text
        self.conversation = SimpleNamespace(id=conversation_id) if conversation_id else None
        self.refusal = refusal


class FakeConversations:
    def __init__(self):
        self.created = 0

    def create(self):
        self.created += 1
        return FakeConversation(f"conv_boot_{self.created}")


class FakeResponses:
    def __init__(self, planner_refusal: bool = False, executor_refusal: bool = False, replan_executor: bool = False):
        self.calls = []
        self.planner_refusal = planner_refusal
        self.executor_refusal = executor_refusal
        self.replan_executor = replan_executor

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        name = kwargs["text"]["format"]["name"]
        if name == "MemoryPatch":
            payload = MemoryPatch(
                schema_version="memory_patch_v3",
                profile_user_name="dni:1234",
                profile_preferred_language="es",
                profile_risk_tolerance=None,
                episodic_append=[],
                working_current_user_goal="cerrar trato",
                working_pending_question=None,
                working_negotiation_stage="proposal",
                relationship_trust_level=None,
                relationship_rapport_level=None,
                relationship_last_interaction_note=None,
                safety_risk_level=None,
                safety_active_domain=None,
                safety_action=None,
                safety_reason=None,
            ).model_dump_json()
            return FakeResponse(f"r{idx}", output_text=payload)

        if name == "PlannerOutput":
            if self.planner_refusal:
                return FakeResponse(f"r{idx}", refusal="planner refusal")
            payload = PlannerOutput.model_validate({
                **arch._planner_fallback().model_dump(mode="json"),
                "policy": {
                    "conversation_act": "answer",
                    "turn_goal": "responder",
                    "ask_clarification": False,
                },
            }).model_dump_json()
            return FakeResponse(f"r{idx}", output_text=payload)

        if self.executor_refusal:
            return FakeResponse(f"r{idx}", refusal="executor refusal")

        conversation_act = "propose" if self.replan_executor else "answer"
        payload = ExecutorOutput(
            schema_version="executor_output_v3",
            status=ExecutorStatus.deliver,
            spoken_text="Texto libre del executor",
            conversation_act_realized=conversation_act,
            memory_used=[],
            tts={"voice_name": "cedar", "speaking_speed": "normal"},
            refusal_reason=None,
        ).model_dump_json()
        return FakeResponse(f"r{idx}", output_text=payload)


class FakeClient:
    def __init__(self, planner_refusal: bool = False, executor_refusal: bool = False, replan_executor: bool = False):
        self.conversations = FakeConversations()
        self.responses = FakeResponses(planner_refusal=planner_refusal, executor_refusal=executor_refusal, replan_executor=replan_executor)


def _turn() -> UserTurn:
    return UserTurn(raw_text="hola", normalized_text="hola", modality="text", language="es", timestamp_utc="2025-01-01T00:00:00Z")


def test_memory_patch_incremental_and_optional_safety():
    c = arch._default_canonical_state()
    patch = MemoryPatch(
        schema_version="memory_patch_v3",
        profile_user_name="dni 999",
        profile_preferred_language=None,
        profile_risk_tolerance="low",
        episodic_append=[MemoryEpisode(event_type="fact", event_summary="precio", turn_id="t1")],
        working_current_user_goal="negociar",
        working_pending_question=None,
        working_negotiation_stage="discovery",
        relationship_trust_level="high",
        relationship_rapport_level=None,
        relationship_last_interaction_note=None,
        safety_risk_level=None,
        safety_active_domain=None,
        safety_action=None,
        safety_reason=None,
    )
    safe_patch = arch._apply_optional_safety_to_memory_patch(patch, arch.SafetyPolicyConfig(hard_baseline_enabled=True, optional_layer_enabled=True))
    apply_memory_patch(c, safe_patch)
    assert c.memory_profile.user_name is None
    assert c.memory_episodic[-1].event_summary == "precio"


def test_build_inputs_specific_and_typed():
    c = arch._default_canonical_state()
    c.recent_messages = [arch.DialogueMessage(role="user", content=str(i)) for i in range(20)]
    planner_input = build_planner_input(c, _turn(), TraceMeta(turn_id="t1", timestamp_utc="z"))
    assert len(planner_input.recent_dialogue) == 8
    assert planner_input.user_turn.normalized_text == "hola"

    executor_input = build_executor_input(c, arch._planner_fallback(), _turn(), TraceMeta(turn_id="t2", timestamp_utc="z"), 2)
    assert len(executor_input.recent_dialogue_short) == 4
    assert executor_input.planner_output.limits.allow_advice is False


def test_bootstrap_conversation_created_once(monkeypatch):
    fake = FakeClient()
    c = arch._default_canonical_state()
    c.openai_thread.mode = ThreadMode.conversation
    c.openai_thread.conversation_id = None

    arch.ensure_openai_thread(fake, c, ThreadMode.conversation)
    first = c.openai_thread.conversation_id
    arch.ensure_openai_thread(fake, c, ThreadMode.conversation)

    assert first is not None
    assert fake.conversations.created == 1


def test_bootstrap_coexists_with_previous_response_mode(monkeypatch):
    fake = FakeClient()
    c = arch._default_canonical_state()
    c.session_settings.thread_mode_override = ThreadMode.previous_response_id
    arch.ensure_openai_thread(fake, c, ThreadMode.conversation)
    assert c.openai_thread.mode == ThreadMode.previous_response_id
    assert fake.conversations.created == 0


def test_thread_chaining_previous_response_id(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(arch, "_build_client", lambda: fake)
    cfg = build_negotiation_pipeline_config().model_copy(update={"thread_mode_default": ThreadMode.previous_response_id})
    session = SessionState(user_id="u1", session_id="s1")

    run_negotiation_cognitive_turn(session, "hola", cfg)
    calls = fake.responses.calls
    assert "previous_response_id" not in calls[0]
    assert calls[1]["previous_response_id"] == "r1"
    assert calls[2]["previous_response_id"] == "r2"


def test_refusal_handling_planner_and_executor(monkeypatch):
    planner_refuse_client = FakeClient(planner_refusal=True)
    monkeypatch.setattr(arch, "_build_client", lambda: planner_refuse_client)
    session = SessionState(user_id="u2", session_id="s2")
    cfg = build_negotiation_pipeline_config()
    _, updated = run_negotiation_cognitive_turn(session, "hola", cfg)
    planner_log = updated.world_state[cfg.memory_key]["trace"]["logs"][1]
    assert planner_log["call_source"] == StructuredCallSource.refusal

    executor_refuse_client = FakeClient(executor_refusal=True)
    monkeypatch.setattr(arch, "_build_client", lambda: executor_refuse_client)
    session2 = SessionState(user_id="u3", session_id="s3")
    _, updated2 = run_negotiation_cognitive_turn(session2, "hola", cfg)
    executor_log = updated2.world_state[cfg.memory_key]["trace"]["logs"][2]
    assert executor_log["call_source"] == StructuredCallSource.refusal


def test_executor_no_replan_enforced_with_safe_text(monkeypatch):
    fake = FakeClient(replan_executor=True)
    monkeypatch.setattr(arch, "_build_client", lambda: fake)
    session = SessionState(user_id="u4", session_id="s4")
    cfg = build_negotiation_pipeline_config()
    reply, updated = run_negotiation_cognitive_turn(session, "hola", cfg)

    assert "confirmo el objetivo" in reply.lower()
    trace = updated.world_state[cfg.memory_key]["trace"]
    assert trace["grades"]["planner_executor_agreement"] is True
    assert "executor_replan_blocked" in trace["logs"][2]["output_status"]


def test_feature_safety_flag_governs_optional_layer(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(arch, "_build_client", lambda: fake)
    session = SessionState(user_id="u5", session_id="s5")
    cfg_off = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False})
    _, updated_off = run_negotiation_cognitive_turn(session, "hola", cfg_off)
    assert updated_off.world_state[cfg_off.memory_key]["memory_profile"]["user_name"] == "dni:1234"

    session2 = SessionState(user_id="u6", session_id="s6")
    cfg_on = build_negotiation_pipeline_config().model_copy(update={"feature_safety": True})
    _, updated_on = run_negotiation_cognitive_turn(session2, "hola", cfg_on)
    assert updated_on.world_state[cfg_on.memory_key]["memory_profile"]["user_name"] is None


def test_hard_baseline_still_on_when_feature_safety_off(monkeypatch):
    fake = FakeClient(replan_executor=True)
    monkeypatch.setattr(arch, "_build_client", lambda: fake)
    session = SessionState(user_id="u7", session_id="s7")
    cfg = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False})
    reply, _ = run_negotiation_cognitive_turn(session, "hola", cfg)
    assert "confirmo el objetivo" in reply.lower()


def test_sdk_compatibility_helper():
    info = check_openai_sdk_compatibility(strict=False)
    assert info.minimum_version == arch.OPENAI_MIN_VERSION
    assert info.status in {arch.SDKCompatibilityStatus.compatible, arch.SDKCompatibilityStatus.below_minimum, arch.SDKCompatibilityStatus.unknown}
