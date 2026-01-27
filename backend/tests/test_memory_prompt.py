import json
from types import SimpleNamespace

from negotiation.context_utils import build_memory_context, maybe_refresh_summary
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


def _summary_payload(extra=None):
    payload = {
        "facts": [],
        "open_questions": [],
        "constraints_limits": [],
        "seller_signals": [],
        "buyer_signals": [],
        "decisions": [],
    }
    if extra:
        payload.update(extra)
    return payload


def _canonical_summary(extra=None):
    return json.dumps(
        _summary_payload(extra),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )


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
    state.summary = _canonical_summary({"facts": ["Resumen antiguo"]})
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

    _, short_memory, _ = build_memory_context(
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
        return json.dumps(
            _summary_payload({"facts": ["Resumen nuevo"]}),
            ensure_ascii=False,
        )

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

    assert json.loads(state.summary)["facts"] == ["Resumen nuevo"]
    assert sum(1 for m in state.history if m.get("role") == "user") <= 2

    executor_user = captured["messages"][1].content
    assert "[LONG_MEMORY]" in executor_user
    assert "[SHORT_MEMORY]" in executor_user


def test_refresh_meta_no_summarizer():
    state = _seed_state()
    state.history = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
    ]

    deps = SimpleNamespace()

    meta = maybe_refresh_summary(
        state,
        deps=deps,
        context_limit_turns=1,
        keep_last_n_turns=1,
    )

    assert meta["reason"] == "no_summarizer"
    assert meta["refreshed"] is False


def test_safe_merge_unstructured_candidate():
    def fake_summarize(existing_summary, new_block):
        return "texto sin headings"

    deps = _base_deps({}, summarize=fake_summarize)
    state = _seed_state()
    state.summary = _canonical_summary({"facts": ["ok"]})
    state.history = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
    ]

    meta = maybe_refresh_summary(
        state,
        deps=deps,
        context_limit_turns=1,
        keep_last_n_turns=1,
    )

    assert meta["refreshed"] is True
    merged = json.loads(state.summary)
    assert merged.get("_unstructured_candidates") == ["texto sin headings"]


def test_summary_refresh_json_candidate_is_canonical():
    def fake_summarize(existing_summary, new_block):
        return json.dumps(
            {
                "decisions": [],
                "buyer_signals": [],
                "seller_signals": [],
                "constraints_limits": [],
                "open_questions": [],
                "facts": ["OK"],
            },
            ensure_ascii=False,
        )

    deps = _base_deps({}, summarize=fake_summarize)
    state = _seed_state()
    state.history = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
    ]

    meta = maybe_refresh_summary(
        state,
        deps=deps,
        context_limit_turns=1,
        keep_last_n_turns=1,
    )

    assert meta["refreshed"] is True
    assert state.summary == _canonical_summary({"facts": ["OK"]})
    parsed = json.loads(state.summary)
    assert "_summary_fallback_invalid" not in parsed
    assert "_unstructured_candidates" not in parsed


def test_memory_context_tolerates_system_and_tool_roles():
    state = _seed_state()
    state.summary = _canonical_summary({"facts": ["OK"]})
    state.history = [
        {"role": "system", "content": "internal note"},
        {"role": "user", "content": "U1"},
        {"role": "tool", "content": "tool output"},
        {"role": "assistant", "content": "A1"},
    ]

    long_memory, short_memory, meta = build_memory_context(
        state.history,
        state.summary,
        keep_last_n_turns=1,
    )

    assert long_memory
    assert "SYSTEM: internal note" in short_memory
    assert meta["turns_total"] == 1

    deps = _base_deps({}, summarize=lambda *_args: _canonical_summary())
    meta_refresh = maybe_refresh_summary(
        state,
        deps=deps,
        context_limit_turns=0,
        keep_last_n_turns=1,
    )
    assert meta_refresh["refreshed"] is True


def test_memory_meta_and_refresh_meta_in_debug_trace(monkeypatch):
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
    state.history = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, encantado."},
    ]

    run_negotiation_agent(state, "Precio?", deps=deps)

    last_trace = state.debug_trace[-1]
    assert "memory_meta" in last_trace
    assert "refresh_meta" in last_trace
