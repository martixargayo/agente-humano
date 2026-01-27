from negotiation.context_utils import build_memory_context
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state
from negotiation.schemas import default_world_state
from state import SessionState


def _base_deps(captured, *, summarize=None):
    def fake_plan_policy(*_args, **_kwargs):
        return default_policy_decision(), {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    return AgentDeps(
        plan_policy=fake_plan_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
        summarize=summarize,
    )


def _seed_state() -> SessionState:
    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    return state


def test_executor_prompt_memory_single_injection(monkeypatch):
    captured = {}
    deps = _base_deps(captured)

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = _seed_state()
    state.summary = "Resumen antiguo"
    state.history = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, encantado."},
    ]

    run_negotiation_agent(state, "Precio?", deps=deps)

    executor_user = captured["messages"][1].content
    assert "[MEMORY]" in executor_user
    assert "[LONG_MEMORY]" in executor_user
    assert "[SHORT_MEMORY]" in executor_user
    assert executor_user.count("Vendedor: Hola") == 1
    assert "[HISTORIAL RECIENTE]" not in executor_user
    assert "[RESUMEN INTERNO" not in executor_user


def test_turn_aware_short_memory_slice():
    history = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "U3"},
        {"role": "assistant", "content": "A3"},
        {"role": "user", "content": "U4"},
        {"role": "assistant", "content": "A4"},
        {"role": "user", "content": "U5"},
        {"role": "assistant", "content": "A5"},
        {"role": "user", "content": "U6"},
        {"role": "assistant", "content": "A6"},
    ]

    _, short_memory = build_memory_context(
        history,
        summary=None,
        keep_last_n_turns=2,
    )

    assert "Vendedor: U4" not in short_memory
    assert short_memory.startswith("Vendedor: U5")
    assert "Vendedor: U5" in short_memory
    assert "Comprador: A5" in short_memory
    assert "Vendedor: U6" in short_memory
    assert "Comprador: A6" in short_memory


def test_summary_refresh_trims_and_updates(monkeypatch):
    captured = {}

    def fake_summarize(existing_summary, new_block):
        return "RESUMEN NUEVO"

    deps = _base_deps(captured, summarize=fake_summarize)

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )
    monkeypatch.setattr("negotiation.negotiation_graph.DEFAULT_CONTEXT_LIMIT_TURNS", 2)
    monkeypatch.setattr("negotiation.negotiation_graph.DEFAULT_KEEP_LAST_TURNS", 2)

    state = _seed_state()
    state.history = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "U3"},
        {"role": "assistant", "content": "A3"},
    ]

    run_negotiation_agent(state, "U4", deps=deps)

    assert state.summary == "RESUMEN NUEVO"
    assert sum(1 for m in state.history if m.get("role") == "user") <= 2

    executor_user = captured["messages"][1].content
    assert "[LONG_MEMORY]" in executor_user
    assert "[SHORT_MEMORY]" in executor_user
