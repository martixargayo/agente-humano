"""Runner manual reproducible para QA de hardening (Mustang)."""

from __future__ import annotations

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.schemas import default_belief_state, default_policy_decision
from negotiation.state.deps import AgentDeps
from state import SessionState


def _deps() -> AgentDeps:
    def fake_plan_phase_policy(**_kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "safe_neutral"
        return {"phase": "climate", "confidence": 0.7, "reasons": ["manual-runner"], "signals": [], "alternatives": []}, decision, {}

    def fake_update_belief_state(**_kwargs):
        return default_belief_state(), {"belief_update_failed": False}

    def fake_execute(_messages):
        return '{"response_text":"Entendido. ¿Cuántos propietarios ha tenido?","asked_question":true,"requested_info_slots":["propietarios"],"tone_used":"neutral","followup_intent":null,"render_meta":{}}'

    return AgentDeps(plan_phase_policy=fake_plan_phase_policy, update_belief_state=fake_update_belief_state, execute=fake_execute)


def run_manual_sequence() -> None:
    turns = [
        "Lo compré nuevo.",
        "Mantenimiento anual con facturas.",
        "No lo compré nuevo, me confundí.",
        "¿Cómo estás?",
        "Vale, sigo: tengo toda la documentación.",
        "Me comprometo a dejar oferta por escrito.",
        "Sigo en la misma línea, sin más detalle.",
        "Sigo en la misma línea, sin más detalle.",
        "Sigo en la misma línea, sin más detalle.",
        "Último dato: un solo propietario.",
    ]

    state = SessionState(user_id="manual", session_id="mustang")
    deps = _deps()

    for idx, msg in enumerate(turns, start=1):
        _, state = run_negotiation_agent(state, msg, deps=deps)
        trace = state.debug_trace[-1]
        progress = trace.get("progress_state", {})
        judgement = trace.get("policy_plan_judgement", {})
        retry = progress.get("retry_guard", {}) if isinstance(progress, dict) else {}
        buckets = ((trace.get("world_new") or {}).get("world_buckets") or {}) if isinstance(trace.get("world_new"), dict) else {}
        bucket_counts = {k: len(v) for k, v in buckets.items() if isinstance(v, list)}
        print(f"turn={idx} plan_id={(progress.get('active_plan') or {}).get('plan_id','')} step_idx={(progress.get('active_plan') or {}).get('current_step_idx',0)} intent_id={((progress.get('active_plan') or {}).get('steps') or [{}])[0].get('intent_id','')}")
        print(f"  judge.plan_status={judgement.get('plan_status','')} skip_planner={judgement.get('skip_planner',False)} missing_signals={judgement.get('missing_signals',[])}")
        print(f"  retry_guard.key={retry.get('active_key','')} attempts={retry.get('attempts',0)} reached={retry.get('reached',False)}")
        print(f"  world_buckets_delta={bucket_counts}")
        print(f"  human_first={trace.get('advisor_recs',{}).get('human_mode','none')} ask_exact={trace.get('assistant_reply','').endswith('¿Cuántos propietarios ha tenido?')}")


if __name__ == "__main__":
    run_manual_sequence()
