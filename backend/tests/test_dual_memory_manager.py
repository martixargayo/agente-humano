from state import SessionState

from negotiation.negotiation_graph import _refresh_dual_memory


class _Deps:
    def __init__(self):
        self.calls = []

    def summarize(self, existing_summary: str, new_block: str) -> str:
        self.calls.append((existing_summary, new_block))
        base = existing_summary.strip()
        chunk = new_block.strip()
        return "\n\n".join([x for x in [base, chunk] if x]).strip()


def _make_session(turns: int) -> SessionState:
    s = SessionState(user_id="u", session_id="s")
    for i in range(1, turns + 1):
        s.history.append({"role": "user", "content": f"u{i}"})
        s.history.append({"role": "assistant", "content": f"a{i}"})
    return s


def test_dual_memory_under_short_limit_keeps_long_empty():
    session = _make_session(4)
    deps = _Deps()
    meta = _refresh_dual_memory(session, deps, short_turns=4)

    progress = session.progress_state
    assert progress["memory_long"] == ""
    assert progress["memory_short"].count("user:") == 4
    assert meta["memory_long_updated"] is False
    assert meta["summarizer_called"] is False


def test_dual_memory_overflow_updates_long_and_short_window():
    session = _make_session(5)
    deps = _Deps()
    meta = _refresh_dual_memory(session, deps, short_turns=4)

    progress = session.progress_state
    assert "user: u2" in progress["memory_short"]
    assert "user: u5" in progress["memory_short"]
    assert "user: u1" not in progress["memory_short"]
    assert meta["memory_long_updated"] is True
    assert meta["summarizer_called"] is True
    assert len(deps.calls) == 1


def test_dual_memory_incremental_updates_only_new_overflow_blocks():
    session = _make_session(5)
    deps = _Deps()
    _refresh_dual_memory(session, deps, short_turns=4)

    # extend conversation to 8 turns and refresh again
    for i in range(6, 9):
        session.history.append({"role": "user", "content": f"u{i}"})
        session.history.append({"role": "assistant", "content": f"a{i}"})

    meta = _refresh_dual_memory(session, deps, short_turns=4)

    progress = session.progress_state
    assert "user: u5" in progress["memory_short"]
    assert "user: u8" in progress["memory_short"]
    assert "user: u4" not in progress["memory_short"]
    assert progress["memory_long_turns_summarized"] == 4
    assert len(deps.calls) == 2
    # second call only summarizes turns u2..u4 (incremental delta)
    assert "user: u2" in deps.calls[1][1]
    assert "user: u4" in deps.calls[1][1]
    assert "user: u1" not in deps.calls[1][1]
    assert meta["memory_long_updated"] is True


def test_short_window_sliding_exact():
    deps = _Deps()
    session = _make_session(8)
    _refresh_dual_memory(session, deps, short_turns=4)
    short_t8 = session.progress_state["memory_short"]
    assert "user: u5" in short_t8
    assert "user: u8" in short_t8
    assert "user: u4" not in short_t8
    assert "user: u9" not in short_t8

    session.history.append({"role": "user", "content": "u9"})
    session.history.append({"role": "assistant", "content": "a9"})
    _refresh_dual_memory(session, deps, short_turns=4)
    short_t9 = session.progress_state["memory_short"]
    assert "user: u6" in short_t9
    assert "user: u9" in short_t9
    assert "user: u5" not in short_t9
    assert "user: u10" not in short_t9


def test_turn_buffer_truncation():
    deps = _Deps()
    session = _make_session(30)
    _refresh_dual_memory(session, deps, short_turns=4)
    assert len(session.progress_state.get("turn_buffer", [])) <= 10
