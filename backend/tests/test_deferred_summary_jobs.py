import json

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.state.deps import AgentDeps
from negotiation.summary_jobs import (
    DeferredSummaryManager,
    SummaryRefreshJob,
    apply_deferred_hard_trim,
)
from state import SESSIONS, SessionState, add_message, get_session_state, save_session_state


def _fake_deps(summarize_fn=None):
    return AgentDeps(
        plan_phase_policy=lambda *args, **kwargs: ({}, {"policy_id": "neutral_anchor"}, {}),
        update_belief_state=lambda *args, **kwargs: ({}, {}),
        execute=lambda *_args, **_kwargs: "ok",
        summarize=summarize_fn,
    )


def _valid_summary(tag: str = "s") -> str:
    return json.dumps(
        {
            "facts": [f"fact-{tag}"],
            "open_questions": [],
            "constraints_limits": [],
            "seller_signals": [],
            "buyer_signals": [],
            "decisions": [],
        }
    )


def _make_job(state: SessionState, *, context_limit_turns: int = 2, keep_last_n_turns: int = 1):
    return SummaryRefreshJob(
        user_id=state.user_id,
        session_id=state.session_id,
        turn_id=state.turn_count,
        expected_turn_count=state.turn_count,
        context_limit_turns=context_limit_turns,
        keep_last_n_turns=keep_last_n_turns,
    )


def test_run_negotiation_agent_deferred_skips_summary_in_critical_path(monkeypatch):
    SESSIONS.clear()
    state = SessionState(user_id="u", session_id="s")

    def _should_not_run(*_args, **_kwargs):
        raise AssertionError("maybe_refresh_summary no debe ejecutarse en critical path")

    def _fake_invoke(graph_state):
        out = dict(graph_state)
        out["response"] = "respuesta"
        return out

    monkeypatch.setenv("NEGOTIATION_DEFER_SUMMARY", "1")
    monkeypatch.setattr("negotiation.negotiation_graph.maybe_refresh_summary", _should_not_run)
    monkeypatch.setattr("negotiation.negotiation_graph.negotiation_app.invoke", _fake_invoke)

    deps = _fake_deps(summarize_fn=lambda *_: _valid_summary("deferred"))
    reply, new_state = run_negotiation_agent(state, "hola", deps=deps)

    assert reply == "respuesta"
    assert new_state.debug_trace[-1]["summary_enqueue_meta"]["source"] == "run_negotiation_agent"


def test_job_applies_summary_and_trims_history_with_job_limits():
    SESSIONS.clear()
    state = SessionState(user_id="u1", session_id="s1")
    for i in range(6):
        add_message(state, "user", f"U{i}")
        add_message(state, "assistant", f"A{i}")
    save_session_state(state)

    manager = DeferredSummaryManager()
    deps = _fake_deps(summarize_fn=lambda *_: _valid_summary("apply"))
    job = _make_job(state, context_limit_turns=2, keep_last_n_turns=1)

    result = manager.run_job_sync(job, deps=deps)
    updated = get_session_state("u1", "s1")

    assert result["job_status"] == "applied"
    assert json.loads(updated.summary)["facts"] == ["fact-apply"]
    assert sum(1 for m in updated.history if m.get("role") == "user") == 1
    assert updated.summary_meta["last_refresh_turn_id"] == state.turn_count


def test_idempotency_and_stale_guard():
    SESSIONS.clear()
    state = SessionState(user_id="u2", session_id="s2")
    for i in range(4):
        add_message(state, "user", f"U{i}")
        add_message(state, "assistant", f"A{i}")
    save_session_state(state)

    manager = DeferredSummaryManager()
    deps = _fake_deps(summarize_fn=lambda *_: _valid_summary("idem"))
    job = _make_job(state)

    assert manager.enqueue(job) is True
    assert manager.enqueue(job) is False
    assert manager.drain_queue(deps=deps) == 1

    stale = manager.run_job_sync(job, deps=deps)
    assert stale["job_status"] == "stale_last_refresh"


def test_race_guard_when_new_turn_arrives_before_job_runs():
    SESSIONS.clear()
    state = SessionState(user_id="u3", session_id="s3")
    for i in range(4):
        add_message(state, "user", f"U{i}")
        add_message(state, "assistant", f"A{i}")
    save_session_state(state)

    manager = DeferredSummaryManager()
    deps = _fake_deps(summarize_fn=lambda *_: _valid_summary("race"))
    job = _make_job(state)

    state2 = get_session_state("u3", "s3")
    add_message(state2, "user", "nuevo")
    save_session_state(state2)

    result = manager.run_job_sync(job, deps=deps)
    updated = get_session_state("u3", "s3")

    assert result["job_status"] == "stale_turn_count"
    assert updated.summary == ""


def test_processed_idempotency_window_is_bounded():
    SESSIONS.clear()
    state = SessionState(user_id="ub", session_id="sb")
    for i in range(8):
        add_message(state, "user", f"U{i}")
        add_message(state, "assistant", f"A{i}")
    save_session_state(state)

    manager = DeferredSummaryManager(max_processed_keys=3)
    deps = _fake_deps(summarize_fn=lambda *_: _valid_summary("bounded"))

    for idx in range(6):
        job = SummaryRefreshJob(
            user_id="ub",
            session_id="sb",
            turn_id=idx + 1,
            expected_turn_count=state.turn_count,
            context_limit_turns=100,
            keep_last_n_turns=1,
        )
        assert manager.enqueue(job) is True

    manager.drain_queue(deps=deps)
    stats = manager.idempotency_stats()
    assert stats["processed_keys"] == 3
    assert stats["processed_order"] == 3


def test_hard_trim_keeps_recent_user_turns_only():
    state = SessionState(user_id="u4", session_id="s4")
    for i in range(10):
        add_message(state, "user", f"U{i}")
        add_message(state, "assistant", f"A{i}")

    changed = apply_deferred_hard_trim(state, max_user_turns=3)

    assert changed is True
    assert sum(1 for m in state.history if m.get("role") == "user") == 3
