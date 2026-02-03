# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from .gate_utils import _split_world_diff
from .elementos.belief_definitions import (
    BELIEF_MODEL,
    BELIEF_TEMPERATURE,
    CRITICAL_FLAGS,
    REASON_PRIORITY,
)
from .elementos.belief.belief_updater_v2_prompts import (
    BELIEF_UPDATER_V2_SYSTEM_PROMPT,
    BELIEF_UPDATER_V2_USER_PROMPT,
    UNIVERSAL_SPEC,
    NEGOTIATION_SPEC,
    OUTPUT_SCHEMA,
)
from .elementos.belief.belief_contracts import UNIVERSAL_LIMITS
from .schemas import BeliefState, PolicyDecision, WorldState, default_belief_state
from .validation import normalize_belief_state, normalize_belief_universal

_belief_llm = ChatOpenAI(model=BELIEF_MODEL, temperature=BELIEF_TEMPERATURE)
logger = logging.getLogger(__name__)


@dataclass
class _BeliefReasonModel:
    weight: float = 0.5
    confidence: float = 0.5
    evidence: str = ""


class _BeliefStateModel:
    @staticmethod
    def _limit_reasons(reasons: dict) -> dict:
        if not isinstance(reasons, dict):
            return {}
        items = sorted(
            reasons.items(),
            key=lambda kv: (
                -(float(kv[1].weight) * float(kv[1].confidence)),
                REASON_PRIORITY.get(str(kv[0]), 999),
                str(kv[0]),
            ),
        )
        return dict(items[:6])


def has_belief_evidence_delta(
    world_diff: dict,
    prev_world: WorldState,
    world: WorldState,
    extractor_meta: dict | None = None,
) -> bool:
    decisions = (extractor_meta or {}).get("decisions", {}) or {}
    if decisions.get("should_update_beliefs") is True:
        return True
    domain, interaction = _split_world_diff(world_diff)
    if domain or interaction:
        return True
    for key in CRITICAL_FLAGS:
        if world.get(key) != prev_world.get(key):
            return True
    if world.get("tone_signal") != prev_world.get("tone_signal"):
        return True
    if (world.get("interaction") or {}) != (prev_world.get("interaction") or {}):
        return True
    prev_hits = set(prev_world.get("tone_marker_hits", []) or [])
    new_hits = set(world.get("tone_marker_hits", []) or []) - prev_hits
    if new_hits:
        return True
    return False


def _safe_json_load(s: str) -> dict:
    s2 = (s or "").strip()
    i = s2.find("{")
    j = s2.rfind("}")
    if i >= 0 and j > i:
        s2 = s2[i : j + 1]
    return json.loads(s2)


def _step_clamp(prev: float, new: float, max_step: float) -> float:
    if new > prev + max_step:
        return prev + max_step
    if new < prev - max_step:
        return prev - max_step
    return new


def _interaction_strong(world: dict, world_diff: dict | None) -> bool:
    inter = world.get("interaction") or {}
    if inter.get("loop_hint"):
        return True
    if inter.get("evasion_detected"):
        return True
    if inter.get("escalation_signal") == "up":
        return True
    return False


def extract_belief_patch_llm_v2(
    user_message: str,
    world_state: dict,
    world_diff: dict,
    prev_belief: dict,
    conversation_mode: str,
) -> tuple[dict, dict, dict]:
    world_state_json = json.dumps(world_state or {}, ensure_ascii=False)
    world_diff_json = json.dumps(world_diff or {}, ensure_ascii=False)
    prev_belief_json = json.dumps(prev_belief or {}, ensure_ascii=False)

    user_prompt = BELIEF_UPDATER_V2_USER_PROMPT.format(
        conversation_mode=conversation_mode,
        user_message=user_message or "",
        world_state_json=world_state_json,
        world_diff_json=world_diff_json,
        prev_belief_json=prev_belief_json,
        output_schema=OUTPUT_SCHEMA.strip(),
        universal_spec=UNIVERSAL_SPEC.strip(),
        negotiation_spec=NEGOTIATION_SPEC.strip(),
    )

    messages = [
        {"role": "system", "content": BELIEF_UPDATER_V2_SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]
    raw = _belief_llm.invoke(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = _safe_json_load(text)

    if data.get("schema_version") != "belief_updater_v2":
        raise ValueError("belief_updater_v2 invalid schema_version")

    uni_patch = dict(data.get("universal_patch") or {})
    neg_patch = dict(data.get("negotiation_patch") or {})
    meta = dict(data.get("meta") or {})
    meta["extractor_version"] = "belief_updater_v2"
    return uni_patch, neg_patch, meta


def merge_belief_universal(
    prev_u: dict,
    patch_u: dict,
    allow_health_change: bool,
    max_step: float,
) -> dict:
    prev_u_n = normalize_belief_universal(prev_u)
    patch_u_n = normalize_belief_universal(patch_u)
    out = dict(prev_u_n)

    pm = prev_u_n.get("metrics") or {}
    nm = patch_u_n.get("metrics") or {}
    out_m = dict(pm)
    for k in ("trust", "cooperation", "clarity", "engagement"):
        out_m[k] = _step_clamp(float(pm.get(k, 0.5)), float(nm.get(k, 0.5)), max_step)
    out["metrics"] = out_m

    pd = prev_u_n.get("dynamics") or {}
    nd = patch_u_n.get("dynamics") or {}
    out_d = dict(pd)
    for k in ("looping", "evasion"):
        out_d[k] = bool(nd.get(k, out_d.get(k, False)))
    out_d["escalation"] = nd.get("escalation", out_d.get("escalation", "none"))
    out_d["commitment"] = nd.get("commitment", out_d.get("commitment", "none"))
    if allow_health_change:
        out_d["interaction_health"] = nd.get(
            "interaction_health", out_d.get("interaction_health", "stable")
        )
    out["dynamics"] = out_d

    pt = prev_u_n.get("tom") or {}
    nt = patch_u_n.get("tom") or {}
    out_t = dict(pt)
    for k in ("other_goals", "other_tactics", "other_belief_about_me"):
        if nt.get(k):
            out_t[k] = nt.get(k)
    out_t["confidence"] = _step_clamp(float(pt.get("confidence", 0.0)), float(nt.get("confidence", 0.0)), 0.15)
    out["tom"] = out_t

    pr = dict(prev_u_n.get("reasons") or {})
    nr = dict(patch_u_n.get("reasons") or {})
    for k, item in nr.items():
        if not item.get("evidence"):
            continue
        if (k not in pr) or (
            float(item.get("confidence", 0.0)) >= float(pr[k].get("confidence", 0.0))
        ):
            pr[k] = item
    out["reasons"] = pr

    return normalize_belief_universal(out)


def _deep_merge_dict_limited(base: dict, patch: dict, max_depth: int = 3, max_keys: int = 120) -> dict:
    if max_depth <= 0:
        return base
    out = dict(base or {})
    for k, v in (patch or {}).items():
        if len(out) >= max_keys and k not in out:
            break
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge_dict_limited(out.get(k, {}), v, max_depth=max_depth - 1, max_keys=max_keys)
        else:
            out[k] = v
    return out


def update_belief_state(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_executed: PolicyDecision | None,
    last_assistant_message: str,
    user_message: str,
    context_snippet: str,
    extractor_meta: dict | None = None,
    force_update: bool = False,
    conversation_mode: str | None = None,
) -> tuple[BeliefState, dict]:
    previous = prev_belief_state or default_belief_state()
    meta = {
        "belief_update_failed": False,
        "belief_update_error": "",
        "belief_update_skipped": False,
    }

    if not force_update:
        if not has_belief_evidence_delta(
            world_diff=world_diff,
            prev_world=prev_world_state,
            world=world_state,
            extractor_meta=extractor_meta,
        ):
            meta["belief_update_skipped"] = True
            return previous, meta

    conversation_mode = conversation_mode or "negotiation"

    try:
        uni_patch, neg_patch, meta_patch = extract_belief_patch_llm_v2(
            user_message=user_message,
            world_state=world_state,
            world_diff=world_diff,
            prev_belief=previous,
            conversation_mode=conversation_mode,
        )
        meta.update(meta_patch)
    except Exception as exc:
        logger.warning("belief_state_updater_unexpected_error=%s", exc)
        meta["belief_update_failed"] = True
        meta["belief_update_error"] = str(exc)
        return previous, meta

    allow_health_change = _interaction_strong(world_state, world_diff)
    prev_uni = previous.get("universal") or {}
    uni_new = merge_belief_universal(
        prev_uni,
        uni_patch,
        allow_health_change=allow_health_change,
        max_step=UNIVERSAL_LIMITS["max_step_metrics"],
    )

    neg_new = previous.get("negotiation") or {}
    if conversation_mode != "negotiation":
        neg_patch = {}
    if neg_patch:
        neg_new = _deep_merge_dict_limited(neg_new, neg_patch, max_depth=3, max_keys=120)

    belief_v2 = {"universal": uni_new, "negotiation": neg_new}
    belief_state, _issues = normalize_belief_state(belief_v2)
    meta.update(
        {
            "allow_health_change": allow_health_change,
            "uni_patch_keys": sorted(list((uni_patch or {}).keys()))[:50],
            "negotiation_patch_keys": sorted(list((neg_patch or {}).keys()))[:50],
        }
    )

    return belief_state, meta
