from __future__ import annotations

from pathlib import Path

from negotiation.config.models import build_chat_openai_kwargs, get_negotiation_model_config
from negotiation.llm_clients import get_planner_llm, reset_negotiation_llm_caches
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from state import SessionState


def _clear_model_env(monkeypatch):
    for key in [
        "NEGOTIATION_WORLD_MODEL",
        "NEGOTIATION_BELIEF_MODEL",
        "NEGOTIATION_PLANNER_MODEL",
        "NEGOTIATION_SUMMARY_MODEL",
        "NEGOTIATION_EXECUTOR_MODEL",
        "NEGOTIATION_EMBEDDINGS_MODEL",
        "NEGOTIATION_RAG_DIR",
        "NEGOCIATION_RAG_DIR",
        "WORLD_EXTRACTOR_MODEL",
        "WORLD_MODEL",
        "BELIEF_MODEL_NAME",
        "PHASE_POLICY_MODEL_NAME",
        "PLANNER_MODEL_NAME",
        "PHASE_POLICY_TEMPERATURE",
        "PLANNER_TEMPERATURE",
        "SUMMARY_MODEL_NAME",
        "EXECUTOR_MODEL_NAME",
        "OPENAI_MODEL_NAME",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_negotiation_model_config_defaults(monkeypatch):
    _clear_model_env(monkeypatch)

    cfg = get_negotiation_model_config()

    assert cfg.world.model == "gpt-4.1-nano"
    assert cfg.belief.model == "gpt-4.1-nano"
    assert cfg.planner.model == "gpt-4.1-nano"
    assert cfg.summary.model == "gpt-4.1-nano"
    assert cfg.executor.model == "gpt-5-nano"




def test_default_rag_dir_is_disabled(monkeypatch):
    _clear_model_env(monkeypatch)

    cfg = get_negotiation_model_config()

    assert cfg.rag_dir == ""
def test_env_override_changes_only_target_component(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("NEGOTIATION_PLANNER_MODEL", "planner-test-model")

    cfg = get_negotiation_model_config()

    assert cfg.planner.model == "planner-test-model"
    assert cfg.world.model == "gpt-4.1-nano"
    assert cfg.belief.model == "gpt-4.1-nano"
    assert cfg.summary.model == "gpt-4.1-nano"
    assert cfg.executor.model == "gpt-5-nano"


def test_legacy_planner_model_name_env_supported(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("PLANNER_MODEL_NAME", "legacy-planner-model")

    cfg = get_negotiation_model_config()

    assert cfg.planner.model == "legacy-planner-model"


def test_legacy_negociation_rag_dir_env_supported(monkeypatch):
    _clear_model_env(monkeypatch)
    monkeypatch.setenv("NEGOCIATION_RAG_DIR", "/tmp/rag-legacy")

    cfg = get_negotiation_model_config()

    assert cfg.rag_dir == "/tmp/rag-legacy"


def test_build_chat_openai_kwargs_includes_streaming_and_reasoning_model_kwargs(monkeypatch):
    _clear_model_env(monkeypatch)
    cfg = get_negotiation_model_config()

    kwargs = build_chat_openai_kwargs(cfg.executor)

    assert kwargs["streaming"] is True
    assert kwargs["model_kwargs"]["reasoning"]["effort"] == "minimal"


def test_build_chat_openai_kwargs_omits_reasoning_for_non_gpt5(monkeypatch):
    _clear_model_env(monkeypatch)
    cfg = get_negotiation_model_config(
        overrides={"executor": {"model": "gpt-4.1-nano", "reasoning_effort": "minimal"}}
    )

    kwargs = build_chat_openai_kwargs(cfg.executor)

    assert "model_kwargs" not in kwargs


def test_llm_getter_respects_env_before_first_use_and_cache_reset(monkeypatch):
    _clear_model_env(monkeypatch)
    reset_negotiation_llm_caches()

    captured: list[dict] = []

    class _DummyLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def _fake_chat_openai(**kwargs):
        captured.append(kwargs)
        return _DummyLLM(**kwargs)

    monkeypatch.setattr("negotiation.llm_clients.ChatOpenAI", _fake_chat_openai)

    monkeypatch.setenv("NEGOTIATION_PLANNER_MODEL", "planner-a")
    get_planner_llm()
    first_model = captured[-1]["model"]

    monkeypatch.setenv("NEGOTIATION_PLANNER_MODEL", "planner-b")
    get_planner_llm()
    second_model_same_cache = captured[-1]["model"]

    reset_negotiation_llm_caches()
    get_planner_llm()
    third_model_after_reset = captured[-1]["model"]

    assert first_model == "planner-a"
    assert second_model_same_cache == "planner-a"
    assert third_model_after_reset == "planner-b"


def test_debug_trace_exposes_effective_models_and_params(monkeypatch):
    monkeypatch.setenv("NEGOTIATION_EXECUTOR_MODEL", "executor-test-model")

    def fake_plan_phase_policy(*_args, **_kwargs):
        return (
            {
                "phase": "climate",
                "confidence": 0.7,
                "reasons": ["history:test"],
                "signals": [],
                "alternatives": [],
            },
            {
                "policy_id": "safe_neutral",
                "reason": "test",
                "micro_goal": "test",
                "risk_posture": "low",
            },
            {},
        )

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_update_failed": False}

    def fake_execute(_messages):
        return (
            '{"schema_version":"world_extractor_v3","universal_domain_patch":{},'
            '"negotiation_domain_patch":{},"universal_patch":{},"open_claims":[]}'
        )

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )

    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    state.progress_state = default_progress_state()

    run_negotiation_agent(state, "hola", deps=deps)

    trace = state.debug_trace[-1]
    assert trace["models_effective"]["world_model"] == "gpt-4.1-nano"
    assert trace["models_effective"]["executor_model"] == "executor-test-model"
    assert trace["params_effective"]["executor"]["reasoning_effort"] == "minimal"


def test_no_legacy_gpt_4o_mini_default_left_in_negotiation_module():
    root = Path(__file__).resolve().parents[1] / "negotiation"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "gpt-4o-mini" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))

    assert offenders == []
