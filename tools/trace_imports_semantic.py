from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent  # noqa: E402
from negotiation.schemas import default_belief_state, default_policy_decision, default_world_state  # noqa: E402
from negotiation.nodes import world_node as world_node_module  # noqa: E402
from state import SessionState  # noqa: E402


class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeJudgeLLM:
    model_name = "fake-judge"

    def invoke(self, _messages):
        payload = {
            "schema_version": "judge_semantic_v1",
            "topic_alignment": "on_topic",
            "reason_short": "trace_imports",
            "semantic_ledger": {
                "lo_que_ya_se_toco": ["precio"],
                "lo_que_ya_pregunte": ["motivo de venta"],
                "lo_que_falta_pero_no_insistire": [],
            },
            "ledger_update_notes": "trace",
        }
        return _FakeLLMResponse(json.dumps(payload, ensure_ascii=False))


def _fake_deps() -> AgentDeps:
    def fake_plan_phase_policy(*_args, **_kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "semantic_ledger"
        phase_candidate = {
            "phase": "clima_humano",
            "confidence": 0.7,
            "reasons": ["trace"],
            "signals": [],
            "alternatives": [],
        }
        meta = {
            "planner_semantic_output": {
                "schema_version": "planner_semantic_v1",
                "phase": "clima_humano",
                "style": "Breve y natural",
                "next_move_hint": "Responder con calidez.",
                "what_not_to_repeat": ["motivo de venta"],
            }
        }
        return phase_candidate, decision, meta

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_meta": {"trace": True}}

    def fake_execute(_messages):
        return json.dumps(
            {
                "schema_version": "executor_v2",
                "response_text": "Te entiendo, gracias por aclararlo.",
                "asked_question": False,
                "requested_info_slots": [],
                "tone_used": "friendly",
                "followup_intent": None,
                "render_meta": {},
            },
            ensure_ascii=False,
        )

    def fake_summarize(existing_summary, new_block):
        return (str(existing_summary or "") + "\n" + str(new_block or "")).strip()

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
        summarize=fake_summarize,
    )


def main() -> int:
    # Evita llamadas reales al LLM del judge durante el smoke.
    world_node_module.get_planner_llm = lambda: _FakeJudgeLLM()

    state = SessionState(user_id="cleanup", session_id="imports")
    deps = _fake_deps()
    run_negotiation_agent(state, "¿Por qué lo vendes?", deps=deps)

    backend_root = str(BACKEND.resolve())
    used = []
    for _, module in sorted(sys.modules.items(), key=lambda kv: kv[0]):
        f = getattr(module, "__file__", None)
        if not f:
            continue
        p = str(Path(f).resolve())
        if backend_root in p:
            used.append(p)

    out_path = ROOT / "docs" / "cleanup_audit" / "imports_used_semantic.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sorted(set(used))) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
