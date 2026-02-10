from __future__ import annotations

import json
import random
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.policies import list_policy_ids
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from negotiation.validation import normalize_phase_state, normalize_policy_decision, normalize_progress_state
from state import SessionState


ALLOWED_POLICY_STATUS = {"inactive", "active", "succeeded", "abandoned", "paused"}
ALLOWED_PLANNER_REQUEST = {"choose_policy", "continue_policy", "replan_policy"}
ALLOWED_PHASES = {"climate", "interests", "options", "adjust", "formalize"}


def _safe_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class PlannerScript:
    responses: list[object] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def plan_phase_policy(self, **kwargs):
        self.calls.append(kwargs)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            if callable(item):
                return item(**kwargs)
            return item
        decision = default_policy_decision()
        decision["policy_id"] = "safe_neutral"
        phase_candidate = {
            "phase": "climate",
            "confidence": 0.7,
            "reasons": ["history:default"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"script": "default"}}


@dataclass
class ExecutorScript:
    outputs: list[object] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str, user_message: str) -> str:
        self.prompts.append(prompt)
        if self.outputs:
            item = self.outputs.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, dict):
                return _safe_json(item)
            return str(item)
        payload = {
            "response_text": f"ok:{user_message[:120]}",
            "asked_question": "?" in user_message,
            "requested_info_slots": [],
            "tone_used": "neutral",
            "followup_intent": None,
            "render_meta": {},
        }
        return _safe_json(payload)


@dataclass
class FakeLLM:
    executor_script: ExecutorScript
    world_overrides: dict[str, dict] | None = None
    current_user_message: str = ""
    executor_calls: list[str] = field(default_factory=list)
    world_calls: list[str] = field(default_factory=list)

    def set_user_message(self, message: str) -> None:
        self.current_user_message = message

    def execute(self, messages: Any) -> str:
        message_list = list(messages or [])
        message_texts = [self._message_text(item) for item in message_list]
        if self._is_world_extractor_prompt(message_texts):
            self.world_calls.append(message_texts[-1] if message_texts else "")
            return self._world_response()
        prompt = message_texts[-1] if message_texts else ""
        self.executor_calls.append(prompt)
        return self.executor_script(prompt, self.current_user_message)

    def _message_text(self, message: Any) -> str:
        if isinstance(message, dict):
            return str(message.get("content", ""))
        if hasattr(message, "content"):
            return str(getattr(message, "content"))
        return str(message or "")

    def _is_world_extractor_prompt(self, message_texts: list[str]) -> bool:
        signature_tokens = (
            "world_extractor_v3",
            "Extract structured updates for world_state",
            "strict JSON extractor",
        )
        joined = "\n".join(message_texts)
        return any(token in joined for token in signature_tokens)

    def _world_response(self) -> str:
        message = (self.current_user_message or "").lower()
        universal_patch = {}
        universal_domain_patch: dict[str, Any] = {}
        negotiation_domain_patch: dict[str, Any] = {}

        if not message.strip():
            universal_domain_patch["message_is_vague"] = True
        if any(ch.isdigit() for ch in message) or "precio" in message:
            negotiation_domain_patch["price_mentioned"] = True
        if "otra oferta" in message or "otro comprador" in message:
            negotiation_domain_patch["other_buyer_claimed"] = True
            negotiation_domain_patch["other_buyer_text"] = "hay otro comprador"
        if "evidencia" in message or "prueba" in message:
            negotiation_domain_patch["evidence_offered"] = True
            negotiation_domain_patch["evidence_text"] = "evidencia mencionada"
        if "document" in message:
            negotiation_domain_patch["docs_claimed"] = True
            negotiation_domain_patch["docs_types"] = ["papeles"]
        if "conces" in message:
            negotiation_domain_patch["concession_made"] = True
            negotiation_domain_patch["concession_text"] = "concesión implícita"
        if "urgente" in message:
            negotiation_domain_patch["urgency_claimed"] = True
            negotiation_domain_patch["urgency_text"] = "urgente"
        if "tenso" in message or "enfado" in message or "!" in message:
            universal_domain_patch["tone_signal"] = "tense"
            universal_domain_patch["tone_confidence"] = 0.8
        else:
            universal_domain_patch["tone_signal"] = "neutral"
            universal_domain_patch["tone_confidence"] = 0.5

        if self.world_overrides:
            universal_domain_patch.update(self.world_overrides.get("universal_domain_patch", {}))
            negotiation_domain_patch.update(self.world_overrides.get("negotiation_domain_patch", {}))
            universal_patch.update(self.world_overrides.get("universal_patch", {}))

        payload = {
            "schema_version": "world_extractor_v3",
            "universal_domain_patch": universal_domain_patch,
            "negotiation_domain_patch": negotiation_domain_patch,
            "universal_patch": universal_patch,
            "open_claims": [],
        }
        return _safe_json(payload)


def fake_update_belief_state(**kwargs):
    prev = kwargs.get("prev_belief_state") or default_belief_state()
    belief = deepcopy(prev)
    world_state = kwargs.get("world_state") or {}
    tone = (
        world_state.get("universal_domain", {}).get("tone_signal")
        or world_state.get("universal_state", {}).get("tone_signal")
    )
    if tone == "tense":
        belief["universal"]["dynamics"]["interaction_health"] = "tense"
    else:
        belief["universal"]["dynamics"]["interaction_health"] = "stable"
    return belief, {"belief_update_failed": False, "belief_update_skipped": False}


@contextmanager
def capture_graph_states(monkeypatch, graph_module):
    captured: list[dict] = []
    original_invoke = graph_module.negotiation_app.invoke

    def _wrapped(graph_state: dict):
        result = original_invoke(graph_state)
        captured.append(result)
        return result

    monkeypatch.setattr(graph_module.negotiation_app, "invoke", _wrapped)
    try:
        yield captured
    finally:
        monkeypatch.setattr(graph_module.negotiation_app, "invoke", original_invoke)


def simulate_conversation(
    turns: Iterable[str],
    deps,
    *,
    initial_state: SessionState | None = None,
    monkeypatch=None,
    graph_module=None,
) -> tuple[SessionState, list[dict], list[dict]]:
    state = initial_state or SessionState(user_id="u", session_id="s")
    if not state.world_state:
        state.world_state = default_world_state()
    if not state.belief_state:
        state.belief_state = default_belief_state()
    if not state.progress_state:
        state.progress_state = default_progress_state()

    graph_states: list[dict] = []
    if monkeypatch and graph_module:
        with capture_graph_states(monkeypatch, graph_module) as captured:
            for message in turns:
                if hasattr(deps, "set_user_message"):
                    deps.set_user_message(message)
                run_negotiation_agent(state, message, deps=deps)
            graph_states = captured
    else:
        for message in turns:
            if hasattr(deps, "set_user_message"):
                deps.set_user_message(message)
            run_negotiation_agent(state, message, deps=deps)
    return state, state.debug_trace, graph_states


def assert_progress_invariants(progress_state: dict) -> None:
    normalized, issues = normalize_progress_state(progress_state)
    assert issues == []
    policy_state = normalized.get("policy_state", {})
    assert policy_state.get("status") in ALLOWED_POLICY_STATUS
    assert policy_state.get("planner_request") in ALLOWED_PLANNER_REQUEST
    assert policy_state.get("step_idx", 0) >= 0
    assert policy_state.get("step_attempts", 0) >= 0
    assert policy_state.get("no_progress_turns", 0) >= 0
    assert len(policy_state.get("slots_required", [])) <= 12

    phase_state = normalized.get("phase_state", {})
    assert phase_state.get("phase") in ALLOWED_PHASES
    confidence = float(phase_state.get("confidence", 0.0))
    assert 0.0 <= confidence <= 1.0
    assert len(phase_state.get("reasons", [])) <= 8


def assert_policy_decision_invariants(policy_decision: dict, allowed_policy_ids: list[str]) -> None:
    normalized, issues = normalize_policy_decision(policy_decision, allowed_policy_ids)
    assert issues == []
    assert normalized.get("policy_id") in allowed_policy_ids


@contextmanager
def trace_guard(tmp_path, name: str, trace: list[dict], graph_states: list[dict]):
    try:
        yield
    except Exception:
        payload = {"trace": trace, "graph_states": graph_states}
        path = tmp_path / f"{name}_trace.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        raise


def random_messages(seed: int, n: int) -> list[str]:
    rnd = random.Random(seed)
    samples = [
        "ok",
        "no sé",
        "precio?",
        "otra oferta",
        "tengo evidencia",
        "documentos",
        "urgente!",
        "🙂🙂🙂",
        "12345",
        "markdown **bold** `code`",
    ]
    return [rnd.choice(samples) for _ in range(n)]


def available_policy_ids() -> list[str]:
    return list_policy_ids()
