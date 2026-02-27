from state import SessionState

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.schemas import default_policy_decision
from negotiation.state.deps import AgentDeps


class _FakeDeps:
    def __init__(self):
        self.prompts: list[str] = []
        self.summarize_calls: list[tuple[str, str]] = []

    def plan_phase_policy(self, *args, **kwargs):
        del args, kwargs
        return (
            {"phase": "clima_humano", "confidence": 0.7, "reasons": [], "signals": [], "alternatives": []},
            default_policy_decision(),
            {
                "planner_semantic_output": {
                    "schema_version": "planner_semantic_v1",
                    "phase": "clima_humano",
                    "style": "Breve y natural.",
                    "next_move_hint": "Responder breve.",
                    "what_not_to_repeat": [],
                }
            },
        )

    def update_belief_state(self, *args, **kwargs):
        del args, kwargs
        return {}, {}

    def execute(self, messages):
        prompt = ""
        if isinstance(messages, list) and len(messages) >= 2:
            prompt = str(getattr(messages[1], "content", "") or "")
        self.prompts.append(prompt)
        return '{"schema_version":"executor_v2","response_text":"ok","tone":"calm","asked_question":false,"requested_info_slots":[],"next_micro_action":"none","render_meta":{}}'

    def summarize(self, existing_summary: str, new_block: str) -> str:
        self.summarize_calls.append((existing_summary, new_block))
        base = existing_summary.strip()
        chunk = new_block.strip()
        return "\n\n".join([x for x in [base, chunk] if x]).strip()


def _run_turns(total_turns: int) -> tuple[SessionState, _FakeDeps]:
    fake = _FakeDeps()
    deps = AgentDeps(
        plan_phase_policy=fake.plan_phase_policy,
        update_belief_state=fake.update_belief_state,
        execute=fake.execute,
        summarize=fake.summarize,
    )
    state = SessionState(user_id="u", session_id="s")
    for idx in range(1, total_turns + 1):
        _, state = run_negotiation_agent(state, f"mensaje {idx}", deps=deps)
    return state, fake


def test_memory_long_persists_and_reaches_executor_prompt_next_turn():
    state, fake = _run_turns(6)
    assert state.debug_trace[-2]["refresh_meta"]["summarizer_called"] is True
    assert str((state.progress_state or {}).get("memory_long") or "").strip() != ""

    turn6_prompt = fake.prompts[-1]
    assert "memory_long_compact:" in turn6_prompt
    assert "memory_long_compact: SIN_RESUMEN_AUN" not in turn6_prompt


def test_memory_short_tail_with_6_turns_is_exact_3_to_6():
    state, _ = _run_turns(6)
    short = str((state.progress_state or {}).get("memory_short") or "")
    assert "user: mensaje 3" in short
    assert "assistant: ok" in short
    assert "user: mensaje 6" in short
    assert "user: mensaje 2" not in short


def test_memory_short_tail_with_8_turns_is_exact_5_to_8():
    state, _ = _run_turns(8)
    short = str((state.progress_state or {}).get("memory_short") or "")
    assert "user: mensaje 5" in short
    assert "user: mensaje 8" in short
    assert "user: mensaje 4" not in short


def test_memory_short_slides_forward_each_turn():
    fake = _FakeDeps()
    deps = AgentDeps(
        plan_phase_policy=fake.plan_phase_policy,
        update_belief_state=fake.update_belief_state,
        execute=fake.execute,
        summarize=fake.summarize,
    )
    state = SessionState(user_id="u", session_id="s")

    for idx in range(1, 10):
        _, state = run_negotiation_agent(state, f"mensaje {idx}", deps=deps)
        if idx < 4:
            continue
        short = str((state.progress_state or {}).get("memory_short") or "")
        first_expected = max(1, idx - 3)
        assert f"user: mensaje {first_expected}" in short
        assert f"user: mensaje {idx}" in short
        if first_expected > 1:
            assert f"user: mensaje {first_expected - 1}" not in short

    render_meta = ((state.debug_trace[-1].get("executor_output") or {}).get("render_meta") or {})
    assert render_meta.get("memory_short_source") == "progress_state"
    assert int(render_meta.get("memory_short_turns_rendered", 0)) == 4
