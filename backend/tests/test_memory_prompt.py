import json
from types import SimpleNamespace

from negotiation.context_utils import build_memory_context, maybe_refresh_summary
from negotiation.context_utils import build_context_snippet, safe_merge_summary, _try_parse_summary_json
from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state
from negotiation.schemas import default_world_state
from prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from state import SessionState


def _base_deps(captured, *, summarize=None):
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
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


def _print_snapshot(state, captured):
    print("\n[SNAPSHOT] state.summary:", state.summary)
    executor_user = None
    messages = captured.get("messages") if isinstance(captured, dict) else None
    if messages and len(messages) > 1:
        executor_user = getattr(messages[1], "content", None)
    print("[SNAPSHOT] executor_user:", executor_user)
    print("[SNAPSHOT] debug_trace_last:", state.debug_trace[-1] if state.debug_trace else None)


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

    try:
        executor_user = captured["messages"][1].content
        assert "[MEMORY]" in executor_user
        assert "[LONG_MEMORY]" in executor_user
        assert "[SHORT_MEMORY]" in executor_user
        assert executor_user.count("Vendedor: Hola") == 1
        assert "[HISTORIAL RECIENTE]" not in executor_user
        assert "[RESUMEN INTERNO" not in executor_user
    except AssertionError:
        _print_snapshot(state, captured)
        raise


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

    try:
        assert json.loads(state.summary)["facts"] == ["Resumen nuevo"]
        assert sum(1 for m in state.history if m.get("role") == "user") <= 2

        executor_user = captured["messages"][1].content
        assert "[LONG_MEMORY]" in executor_user
        assert "[SHORT_MEMORY]" in executor_user
    except AssertionError:
        _print_snapshot(state, captured)
        raise


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
    assert merged == _summary_payload({"facts": ["ok"]})


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
    assert "facts" in parsed


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
    assert "SYSTEM: internal note" not in short_memory
    assert "TOOL: tool output" in short_memory
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

    try:
        last_trace = state.debug_trace[-1]
        assert "memory_meta" in last_trace
        assert "refresh_meta" in last_trace
    except AssertionError:
        _print_snapshot(state, captured)
        raise


def test_smoke_run_negotiation_agent_without_normalize_patch(monkeypatch):
    monkeypatch.setattr("negotiation.negotiation_graph.get_negotiation_rag_index", lambda: None)
    monkeypatch.setattr(
        "normalizer.normalizer_llm",
        SimpleNamespace(invoke=lambda *_args, **_kwargs: SimpleNamespace(content="ok")),
    )

    captured = {}
    deps = _base_deps(captured)

    state = _seed_state()
    state.summary = _canonical_summary({"facts": ["OK"]})
    state.history = [{"role": "user", "content": "Hola"}]

    run_negotiation_agent(state, "Precio?", deps=deps)

    assert state.debug_trace, "Debe dejar rastro en debug_trace"


def test_summary_prompt_forbids_extra_keys():
    text = (SUMMARY_SYSTEM_PROMPT + "\n" + SUMMARY_USER_PROMPT).lower()
    assert "no añadas claves" in text or "no añadas campos" in text


def test_safe_merge_does_not_invent_schema_keys():
    existing = json.dumps(_summary_payload(), ensure_ascii=False)
    merged = safe_merge_summary(existing, "texto no json")
    obj = json.loads(merged)
    allowed = set(_summary_payload().keys())
    assert set(obj.keys()).issubset(allowed)


def test_try_parse_summary_json_rejects_wrong_types():
    bad = """{
      "facts": "no-list",
      "open_questions": [],
      "constraints_limits": [],
      "seller_signals": [],
      "buyer_signals": [],
      "decisions": []
    }"""
    assert _try_parse_summary_json(bad) is None


def test_try_parse_summary_json_rejects_non_string_items():
    bad = """{
      "facts": [123],
      "open_questions": [],
      "constraints_limits": [],
      "seller_signals": [],
      "buyer_signals": [],
      "decisions": []
    }"""
    assert _try_parse_summary_json(bad) is None


def test_long_memory_rejects_non_json_summary():
    history = [{"role": "user", "content": "U1"}, {"role": "assistant", "content": "A1"}]
    long_memory, short_memory, _ = build_memory_context(
        history, "legacy summary", keep_last_n_turns=1
    )
    assert long_memory == ""
    assert "Vendedor: U1" in short_memory


def test_merge_legacy_to_fallback_json_is_stable():
    merged = safe_merge_summary("legacy summary", "also legacy")
    obj = json.loads(merged)
    required = set(_summary_payload().keys())
    assert set(obj.keys()) >= required


def test_context_snippet_does_not_embed_raw_json_fragment():
    big = json.dumps(
        _summary_payload({"facts": ["x" * 500]}),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    history = [{"role": "user", "content": "U1"}, {"role": "assistant", "content": "A1"}]
    snippet = build_context_snippet(history, big, seller_only=True)
    assert "Resumen breve:" not in snippet or "{" not in snippet


def test_short_memory_excludes_system_before_user_by_design():
    summary = json.dumps(_summary_payload(), ensure_ascii=False)
    history = [
        {"role": "system", "content": "internal note"},
        {"role": "user", "content": "U1"},
        {"role": "tool", "content": "tool out"},
        {"role": "assistant", "content": "A1"},
    ]
    long_memory, short_memory, _ = build_memory_context(history, summary, keep_last_n_turns=1)
    assert "SYSTEM: internal note" not in short_memory
    assert "Vendedor: U1" in short_memory
    assert "TOOL: tool out" in short_memory
    assert "Comprador: A1" in short_memory


def test_history_items_missing_fields_do_not_crash_memory_pipeline():
    s = SessionState(user_id="u", session_id="s")
    s.summary = json.dumps(_summary_payload(), ensure_ascii=False)
    s.history = [
        {"role": "user"},
        {"content": "hi"},
        {"role": "tool", "content": ""},
        {"role": "assistant", "content": "A"},
    ]

    long_memory, short_memory, meta = build_memory_context(
        s.history, s.summary, keep_last_n_turns=1
    )
    assert isinstance(long_memory, str)
    assert isinstance(short_memory, str)
    assert isinstance(meta, dict)

    meta2 = maybe_refresh_summary(
        s, deps=SimpleNamespace(), context_limit_turns=0, keep_last_n_turns=1
    )
    assert meta2["refreshed"] in (True, False)


def test_derive_max_total_cost_clamps_negative_margin():
    from state import derive_max_total_cost

    exit_option = {"label": "x", "total_cost": 100.0, "notes": ""}
    max_cost, _ = derive_max_total_cost(exit_option, margin=-0.5)
    assert max_cost == 100.0


def test_debug_trace_contains_margin(monkeypatch):
    from negotiation.schemas import default_policy_decision, default_belief_state

    monkeypatch.setenv("MAX_TOTAL_COST_MARGIN", "0.10")
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )
    s = _seed_state()
    s.world_state = default_world_state()
    s.progress_state = default_progress_state()

    deps = AgentDeps(
        plan_phase_policy=lambda *_a, **_k: (
            {
                "phase": "opening",
                "confidence": 0.6,
                "reasons": ["history:mock"],
                "signals": [],
                "alternatives": [],
            },
            default_policy_decision(),
            {},
        ),
        update_belief_state=lambda *_a, **_k: (default_belief_state(), {}),
        execute=lambda msgs: "ok",
        summarize=None,
    )

    run_negotiation_agent(s, "Precio?", deps=deps)
    last = s.debug_trace[-1]
    assert last.get("max_total_cost_margin") == 0.10


def test_refresh_meta_reports_invalid_json_candidate():
    def fake_summarize(_existing, _block):
        return json.dumps(
            {
                "facts": ["ok", 1],
                "open_questions": [],
                "constraints_limits": [],
                "seller_signals": [],
                "buyer_signals": [],
                "decisions": [],
            },
            ensure_ascii=False,
        )

    deps = _base_deps({}, summarize=fake_summarize)
    state = _seed_state()
    state.summary = _canonical_summary({"facts": ["prev"]})
    state.history = [{"role": "user", "content": "U1"}, {"role": "assistant", "content": "A1"}]

    meta = maybe_refresh_summary(state, deps=deps, context_limit_turns=0, keep_last_n_turns=1)

    assert meta["refreshed"] is True
    assert meta.get("merge_used_existing") is True
    assert meta.get("candidate_invalid") is True


def test_canonicalization_normalizes_spacing_and_order():
    candidate = (
        '{"open_questions":[],"facts":["OK"],"constraints_limits":[],'
        '"seller_signals":[],"buyer_signals":[],"decisions":[]}'
    )
    merged = safe_merge_summary("", candidate)
    assert merged == _canonical_summary({"facts": ["OK"]})


def test_slice_when_keep_exceeds_turns_excludes_prefix_before_first_user():
    history = [
        {"role": "system", "content": "S"},
        {"role": "tool", "content": "T"},
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
    ]
    _, short_memory, _ = build_memory_context(history, _canonical_summary(), keep_last_n_turns=99)
    assert "SYSTEM: S" not in short_memory
    assert "TOOL: T" not in short_memory
    assert "Vendedor: U1" in short_memory


def test_context_snippet_summary_is_not_json_like():
    big = json.dumps(
        _summary_payload({"facts": ["x" * 200]}),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    history = [{"role": "user", "content": "U1"}, {"role": "assistant", "content": "A1"}]
    snippet = build_context_snippet(history, big, seller_only=True)

    if "Resumen breve:" in snippet:
        forbidden = ["{", "}", "\"", "[", "]"]
        assert all(ch not in snippet for ch in forbidden), snippet


def test_safe_merge_fallback_is_exact_schema_only():
    merged = safe_merge_summary("bad", "worse")
    obj = json.loads(merged)
    assert obj == _summary_payload()
