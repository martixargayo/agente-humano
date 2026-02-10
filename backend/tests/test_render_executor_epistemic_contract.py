from negotiation.executor.render_executor import summarize_belief_state_for_executor
from negotiation.schemas import default_belief_state


def test_executor_summary_excludes_raw_hypotheses_in_governing_block():
    belief = default_belief_state()
    belief["negotiation"]["hypotheses"] = ["bluff"]
    belief["universal"]["behavior_guidance"]["epistemic_style"] = "hedged"
    summary = summarize_belief_state_for_executor(belief)
    payload = summary["summary"]
    assert "behavior_guidance" in (payload.get("universal") or {})
    assert (payload.get("universal") or {}).get("behavior_guidance", {}).get("epistemic_style") == "hedged"
