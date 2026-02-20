from __future__ import annotations

import hashlib
import json
from typing import Any

from .extractors.belief_extractor_v1 import extract_belief_state_llm_v1
from .llm_clients import get_belief_llm
from .schemas import BeliefState, WorldState, default_belief_state
from .validation import normalize_belief_buckets


_CRITICAL_NEGOTIATION_FLAGS = (
    "deadline_claimed",
    "urgency_claimed",
    "other_buyer_exists",
)


def _belief_fingerprint(state: dict) -> str:
    payload = json.dumps(state or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _limit_reasons(reasons: dict[str, dict[str, Any]], max_items: int = 6) -> dict[str, dict[str, Any]]:
    ranked = sorted(
        (reasons or {}).items(),
        key=lambda kv: (
            -float((kv[1] or {}).get("weight", 0.0) or 0.0),
            -float((kv[1] or {}).get("confidence", 0.0) or 0.0),
            kv[0],
        ),
    )
    return {key: value for key, value in ranked[:max_items]}


def has_belief_evidence_delta(
    world_diff: dict,
    prev_world_state: WorldState,
    world_state: WorldState,
    extractor_meta: dict | None = None,
) -> bool:
    decisions = ((extractor_meta or {}).get("decisions") or {}) if isinstance(extractor_meta, dict) else {}
    should_update = decisions.get("should_update_beliefs")
    if should_update is True:
        return True
    if should_update is False:
        return False

    prev_negotiation = (prev_world_state or {}).get("negotiation") if isinstance(prev_world_state, dict) else {}
    curr_negotiation = (world_state or {}).get("negotiation") if isinstance(world_state, dict) else {}
    for key in _CRITICAL_NEGOTIATION_FLAGS:
        if bool((prev_negotiation or {}).get(key)) != bool((curr_negotiation or {}).get(key)):
            return True

    prev_tone = ((prev_world_state or {}).get("universal_domain") or {}).get("tone_signal")
    curr_tone = ((world_state or {}).get("universal_domain") or {}).get("tone_signal")
    if str(prev_tone or "") != str(curr_tone or ""):
        return True

    return bool(world_diff)


def merge_belief_buckets_update_not_rewrite(prev: dict, patch: dict) -> dict:
    limits = {"hypotheses": 6, "strategy_notes": 3, "risk_flags": 3, "watch_items": 3}
    out = {k: list(v) for k, v in normalize_belief_buckets(prev).items()}
    incoming = normalize_belief_buckets(patch)

    def _key(text: str) -> str:
        return str(text or "").strip().lower()

    for bucket, max_items in limits.items():
        index = {_key(it.get("text", "")): dict(it) for it in out.get(bucket, []) if isinstance(it, dict)}
        for item in incoming.get(bucket, []):
            key = _key(item.get("text", ""))
            if not key:
                continue
            prev_item = index.get(key)
            if prev_item is None or float(item.get("confidence", 0.0)) >= float(prev_item.get("confidence", 0.0)):
                index[key] = dict(item)
        vals = sorted(index.values(), key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:max_items]
        out[bucket] = vals
    return out


class _BeliefDeps:
    def execute(self, messages: Any):
        return get_belief_llm().invoke(messages)


def update_belief_state_compat(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_executed: dict | None = None,
    last_assistant_message: str = "",
    user_message: str = "",
    context_snippet: str = "",
    extractor_meta: dict | None = None,
    force_update: bool = True,
    conversation_mode: str = "general",
) -> tuple[BeliefState, dict]:
    del prev_world_state, world_diff, last_policy_executed, last_assistant_message, context_snippet, extractor_meta, force_update, conversation_mode
    previous = dict(prev_belief_state or default_belief_state())
    try:
        belief_state, llm_meta = extract_belief_state_llm_v1(
            deps=_BeliefDeps(),
            user_message=user_message,
            world_state=world_state,
            prev_belief_state=previous,
            turn_idx=int((world_state or {}).get("world_state_meta", {}).get("turn_idx", 0) or 0),
        )
        before_fp = _belief_fingerprint(previous)
        after_fp = _belief_fingerprint(belief_state)
        meta = {
            "belief_update_failed": False,
            "belief_update_error": "",
            "belief_update_skipped": False,
            "belief_merge_changed": before_fp != after_fp,
            "belief_updated_fields": sorted(list(belief_state.keys())),
            "belief_latency_ms": int(llm_meta.get("belief_latency_ms", 0) or 0),
            "belief_noop_reason": "" if before_fp != after_fp else "merge_no_effect",
            "belief_gate_skip_reason": "",
            "belief_node_entered": True,
            "belief_updater_invoked": True,
            "belief_engine": "llm_belief_extractor_v1",
            "belief_llm_used": True,
        }
        return belief_state, meta
    except Exception as exc:
        return previous, {
            "belief_update_failed": True,
            "belief_update_error": str(exc),
            "belief_update_skipped": True,
            "belief_merge_changed": False,
            "belief_updated_fields": [],
            "belief_latency_ms": 0,
            "belief_noop_reason": "llm_error_reuse_prev",
            "belief_gate_skip_reason": "belief_llm_error",
            "belief_node_entered": True,
            "belief_updater_invoked": True,
            "belief_engine": "llm_belief_extractor_v1",
            "belief_llm_used": True,
        }


update_belief_state = update_belief_state_compat
