# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import re

from .llm_clients import get_belief_llm
from .gate_utils import _split_world_diff
from .elementos.belief_definitions import CRITICAL_FLAGS, REASON_PRIORITY
from .elementos.belief.belief_updater_v2_prompts import (
    BELIEF_UPDATER_V2_SYSTEM_PROMPT,
    BELIEF_UPDATER_V2_USER_PROMPT,
    UNIVERSAL_SPEC,
    NEGOTIATION_SPEC,
    OUTPUT_SCHEMA,
    BELIEF_BUCKET_RULES,
)

from .elementos.belief.belief_contracts import UNIVERSAL_LIMITS
from .schemas import BeliefState, PolicyDecision, WorldState, default_belief_state
from .validation import normalize_belief_state, normalize_belief_state_v2, normalize_belief_universal, normalize_belief_buckets
from .belief_governor import derive_behavior_guidance
from .world_belief_adapters import world_v1_to_v2


logger = logging.getLogger(__name__)

BELIEF_MODEL = os.getenv("NEGOTIATION_BELIEF_MODEL") or os.getenv("BELIEF_MODEL_NAME", "gpt-4o-mini")
BELIEF_TEMPERATURE = float(
    os.getenv("NEGOTIATION_BELIEF_TEMPERATURE")
    or os.getenv("BELIEF_TEMPERATURE", "0.2")
)


def _limit_reasons(reasons: dict) -> dict:
    if not isinstance(reasons, dict):
        return {}
    items = sorted(
        reasons.items(),
        key=lambda kv: (
            -(float(kv[1].get("weight", 0.0)) * float(kv[1].get("confidence", 0.0))),
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
    """API externa: se usa cuando force_update=False en flujos no-gated."""
    decisions = (extractor_meta or {}).get("decisions", {}) or {}
    if decisions.get("should_update_beliefs") is True:
        return True
    domain, interaction = _split_world_diff(world_diff)
    if domain or interaction:
        return True
    prev_neg = prev_world.get("negotiation", {}) if isinstance(prev_world, dict) else {}
    prev_uni = prev_world.get("universal_domain", {}) if isinstance(prev_world, dict) else {}
    neg = world.get("negotiation", {}) if isinstance(world, dict) else {}
    uni = world.get("universal_domain", {}) if isinstance(world, dict) else {}
    for key in CRITICAL_FLAGS:
        if key in uni or key in prev_uni:
            if uni.get(key) != prev_uni.get(key):
                return True
        elif key in neg or key in prev_neg:
            if neg.get(key) != prev_neg.get(key):
                return True
    if uni.get("tone_signal") != prev_uni.get("tone_signal"):
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
    interaction = (world or {}).get("universal_v2", {}).get("interaction", {}) if isinstance(world, dict) else {}
    if float(interaction.get("friction", 0.0) or 0.0) >= 0.35:
        return True
    if float(interaction.get("commitment_signal", 0.0) or 0.0) >= 0.35:
        return True
    if isinstance(world_diff, dict):
        domain = world_diff.get("domain", {}) if isinstance(world_diff.get("domain"), dict) else {}
        if "universal_state" in domain or "open_claims" in domain:
            return True
    return False


def _micro_negotiation_patch_from_world(world_state: dict, prev_belief: dict) -> dict:
    patch: dict = {}
    neg = (world_state or {}).get("negotiation", {}) if isinstance(world_state, dict) else {}
    uni = (world_state or {}).get("universal_state", {}) if isinstance(world_state, dict) else {}
    open_claims = (world_state or {}).get("open_claims", []) if isinstance(world_state, dict) else []
    prev_stance = ((prev_belief or {}).get("negotiation", {}) or {}).get("stance", {})
    time_pressure = float(prev_stance.get("time_pressure", 0.5) or 0.5)
    if neg.get("urgency_claimed"):
        time_pressure = max(time_pressure, 0.7)
    goal_txt = str(((uni.get("goal") or {}).get("summary", "")) if isinstance(uni, dict) else "").lower()
    if "antes posible" in goal_txt or "cuanto antes" in goal_txt or "urg" in goal_txt:
        time_pressure = max(time_pressure, 0.68)
    if any((c or {}).get("label") == "market_demand_uncertainty" for c in (open_claims or []) if isinstance(c, dict)):
        time_pressure = max(time_pressure, 0.65)
    urgency_text = str(neg.get("urgency_text", "") or "").strip()
    urgency_reason = str(neg.get("urgency_reason", "") or "").strip()
    if time_pressure > float(prev_stance.get("time_pressure", 0.5) or 0.5):
        patch["stance"] = {"time_pressure": min(time_pressure, 1.0)}
    if neg.get("urgency_claimed") and urgency_reason:
        patch.setdefault("reasons", {})["urgency_signal"] = {
            "weight": min(1.0, max(0.4, time_pressure)),
            "confidence": 0.7,
            "evidence": urgency_text[:180],
        }
    return patch




def _pre_patch_from_world(world_state: dict, prev_belief: dict) -> tuple[dict, dict]:
    neg_patch = _micro_negotiation_patch_from_world(world_state, prev_belief)
    uni_patch: dict = {}
    if not neg_patch:
        return uni_patch, neg_patch

    stance = (neg_patch.get("stance") or {}) if isinstance(neg_patch.get("stance"), dict) else {}
    tp = float(stance.get("time_pressure", 0.5) or 0.5)
    guidance = {
        "pace_preference": min(1.0, max(0.0, 0.5 + max(0.0, tp - 0.5))),
        "verification_need": min(1.0, max(0.0, 0.5 + max(0.0, tp - 0.6))),
    }
    uni_patch = {"behavior_guidance": guidance}
    return uni_patch, neg_patch


def _safe_parse_belief_json(raw_text: str) -> tuple[dict, dict]:
    text = (raw_text or "").strip()
    parse_meta = {
        "belief_parse_ok": False,
        "belief_parse_error": "",
        "belief_json_repair_used": False,
        "belief_json_repair_type": "",
    }
    if not text:
        parse_meta["belief_parse_error"] = "empty_belief_response"
        raise ValueError("empty_belief_response")
    i = text.find("{")
    j = text.rfind("}")
    if i >= 0 and j > i:
        text = text[i : j + 1]
    try:
        data = json.loads(text)
        parse_meta["belief_parse_ok"] = True
        return data, parse_meta
    except Exception as first_error:
        repaired = re.sub(r",\s*([}\]])", r"\1", text)
        repaired = repaired.replace("“", '"').replace("”", '"')
        repaired = re.sub(r"\bNaN\b|\bInfinity\b|-Infinity", "null", repaired)
        parse_meta["belief_json_repair_used"] = True
        parse_meta["belief_json_repair_type"] = "trailing_comma_quotes_nan"
        try:
            data = json.loads(repaired)
            parse_meta["belief_parse_ok"] = True
            return data, parse_meta
        except Exception as second_error:
            parse_meta["belief_parse_error"] = str(second_error)
            raise ValueError(f"parse_error: {second_error}") from first_error


def merge_belief_buckets_update_not_rewrite(prev: dict, patch: dict) -> dict:
    limits = {"hypotheses": 6, "strategy_notes": 3, "risk_flags": 3, "watch_items": 3}
    out = {k: list(v) for k, v in normalize_belief_buckets(prev).items()}
    incoming = normalize_belief_buckets(patch)

    def _key(bucket: str, text: str) -> str:
        base = str(text or "").strip().lower()
        if bucket == "hypotheses":
            base = re.sub(r"\s*\([0-9]+(?:\.[0-9]+)?\)\s*$", "", base)
        return base

    for bucket, max_items in limits.items():
        index = {_key(bucket, it.get("text", "")): dict(it) for it in out.get(bucket, []) if isinstance(it, dict)}
        for item in incoming.get(bucket, []):
            key = _key(bucket, item.get("text", ""))
            if not key:
                continue
            prev_item = index.get(key)
            if prev_item is None or float(item.get("confidence", 0.0)) >= float(prev_item.get("confidence", 0.0)):
                index[key] = dict(item)
        vals = sorted(index.values(), key=lambda d: float(d.get("confidence", 0.0)), reverse=True)[:max_items]
        out[bucket] = vals
    return out


def _bucket_counts(buckets: dict | None) -> dict:
    buckets = buckets or {}
    return {
        "hypotheses": len(buckets.get("hypotheses", []) if isinstance(buckets.get("hypotheses"), list) else []),
        "strategy_notes": len(buckets.get("strategy_notes", []) if isinstance(buckets.get("strategy_notes"), list) else []),
        "risk_flags": len(buckets.get("risk_flags", []) if isinstance(buckets.get("risk_flags"), list) else []),
        "watch_items": len(buckets.get("watch_items", []) if isinstance(buckets.get("watch_items"), list) else []),
    }


def _count_confidence_out_of_range(buckets: dict | None) -> int:
    buckets = buckets or {}
    count = 0
    for key in ("hypotheses", "strategy_notes", "risk_flags", "watch_items"):
        vals = buckets.get(key, []) if isinstance(buckets.get(key), list) else []
        for item in vals:
            if not isinstance(item, dict):
                continue
            try:
                c = float(item.get("confidence", 0.0) or 0.0)
            except Exception:
                c = 0.0
            if c < 0.0 or c > 1.0:
                count += 1
    return count


def _belief_fingerprint(state: dict) -> str:
    payload = json.dumps(state or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_preview(value: object, max_chars: int = 300) -> str:
    try:
        txt = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        txt = str(value)
    txt = re.sub(r"https?://\S+", "[url]", txt)
    txt = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", txt)
    txt = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[phone]", txt)
    return txt[:max_chars]


def extract_belief_patch_llm_v3(
    user_message: str,
    world_state: dict,
    world_diff: dict,
    prev_belief: dict,
    conversation_mode: str,
) -> tuple[dict, dict, dict, dict]:
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
        belief_bucket_rules=BELIEF_BUCKET_RULES.strip(),
    )

    prompt_hash = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    messages = [
        {"role": "system", "content": BELIEF_UPDATER_V2_SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]
    llm = get_belief_llm()
    t0 = time.perf_counter()
    raw = llm.invoke(messages)
    llm_latency_ms = (time.perf_counter() - t0) * 1000.0
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data, parse_meta = _safe_parse_belief_json(text)

    if data.get("schema_version") != "belief_updater_v2":
        raise ValueError("belief_updater_v2 invalid schema_version")

    uni_patch = dict(data.get("universal_patch") or {})
    neg_patch = dict(data.get("negotiation_patch") or {})
    belief_buckets_patch = dict(data.get("belief_buckets_patch") or {})
    meta = dict(data.get("meta") or {})
    meta["extractor_version"] = "belief_updater_v3"
    meta["belief_llm_used"] = True
    meta["belief_llm_model"] = str(getattr(llm, "model", ""))
    meta["belief_llm_prompt_hash"] = prompt_hash
    meta["belief_llm_latency_ms"] = round(float(llm_latency_ms), 3)
    meta["belief_llm_raw_response_preview"] = _safe_preview(text or "", max_chars=500)
    meta.update(parse_meta)
    meta["belief_patch_keys"] = [
        key
        for key in ("universal_patch", "negotiation_patch", "belief_buckets_patch", "meta")
        if key in data
    ]
    meta["belief_patch_preview"] = _safe_preview(
        {
            "universal_patch": uni_patch,
            "negotiation_patch": neg_patch,
            "belief_buckets_patch": belief_buckets_patch,
        }
    )
    return uni_patch, neg_patch, belief_buckets_patch, meta


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
    out["reasons"] = _limit_reasons(pr)

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
    started = time.perf_counter()
    previous = prev_belief_state or default_belief_state()
    meta = {
        "belief_update_failed": False,
        "belief_update_error": "",
        "belief_update_skipped": False,
        "belief_llm_failed": False,
        "belief_updated_via_fallback": False,
        "belief_node_entered": True,
    }

    if not force_update:
        if not has_belief_evidence_delta(
            world_diff=world_diff,
            prev_world=prev_world_state,
            world=world_state,
            extractor_meta=extractor_meta,
        ):
            meta["belief_update_skipped"] = True
            meta["belief_latency_ms"] = int((time.perf_counter() - started) * 1000)
            return previous, meta


    conversation_mode = conversation_mode or "negotiation"

    pre_uni_patch, pre_neg_patch = _pre_patch_from_world(world_state, previous)

    llm_failed = False
    parse_error_message = ""
    try:
        uni_patch, neg_patch, belief_buckets_patch, meta_patch = extract_belief_patch_llm_v3(
            user_message=user_message,
            world_state=world_state,
            world_diff=world_diff,
            prev_belief=previous,
            conversation_mode=conversation_mode,

        )
        meta.update(meta_patch)
    except Exception as exc:
        logger.warning("belief_state_updater_unexpected_error=%s", exc)
        llm_failed = True
        parse_error_message = str(exc)
        meta["belief_llm_failed"] = True
        meta["belief_update_error"] = str(exc)
        meta["belief_fallback_used"] = True
        meta["belief_fallback_reason"] = "parse_error"
        meta["belief_error"] = str(exc)
        meta["belief_updated_via_fallback"] = True
        uni_patch, neg_patch, belief_buckets_patch = {}, {}, {}
        meta.setdefault("belief_llm_used", True)
        meta.setdefault("belief_llm_raw_response_preview", "")
        meta.setdefault("belief_parse_ok", False)
        meta.setdefault("belief_parse_error", str(exc))
        meta.setdefault("belief_json_repair_used", False)
        meta.setdefault("belief_json_repair_type", "")
        meta.setdefault("belief_patch_keys", [])
        meta.setdefault("belief_patch_preview", "")

    if pre_uni_patch and not llm_failed:
        uni_patch = _deep_merge_dict_limited(pre_uni_patch, uni_patch, max_depth=3, max_keys=40)
    if pre_neg_patch and not llm_failed:
        neg_patch = _deep_merge_dict_limited(pre_neg_patch, neg_patch, max_depth=3, max_keys=60)

    allow_health_change = _interaction_strong(world_state, world_diff)
    prev_uni = previous.get("universal") or {}
    uni_new = merge_belief_universal(
        prev_uni,
        uni_patch,
        allow_health_change=allow_health_change,
        max_step=UNIVERSAL_LIMITS["max_step_metrics"],
    )

    neg_new = previous.get("negotiation") or {}
    if conversation_mode != "negotiation" and not llm_failed:
        micro_patch = _micro_negotiation_patch_from_world(world_state, previous)
        if micro_patch:
            neg_patch = _deep_merge_dict_limited(neg_patch, micro_patch, max_depth=2, max_keys=40)
        else:
            neg_patch = {}
    if neg_patch:
        neg_new = _deep_merge_dict_limited(neg_new, neg_patch, max_depth=3, max_keys=120)

    belief_before_fingerprint = _belief_fingerprint(previous)
    raw_bucket_keys = sorted(list((belief_buckets_patch or {}).keys())) if isinstance(belief_buckets_patch, dict) else []
    raw_patch_counts = _bucket_counts(belief_buckets_patch if isinstance(belief_buckets_patch, dict) else {})
    confidence_clamps = _count_confidence_out_of_range(belief_buckets_patch if isinstance(belief_buckets_patch, dict) else {})
    normalized_buckets_patch = normalize_belief_buckets(belief_buckets_patch)
    normalized_patch_counts = _bucket_counts(normalized_buckets_patch)
    belief_dropped_fields = [k for k in raw_bucket_keys if k not in normalized_buckets_patch]

    belief_v2 = {"schema_version": "v2", "universal": uni_new, "negotiation": neg_new}
    belief_state, _issues = normalize_belief_state_v2(belief_v2)
    prev_buckets = (previous or {}).get("belief_buckets", {}) if isinstance(previous, dict) else {}
    belief_state["belief_buckets"] = merge_belief_buckets_update_not_rewrite(prev_buckets, normalized_buckets_patch)
    if llm_failed:
        belief_state = dict(previous)
        if "belief_buckets" in belief_state or prev_buckets:
            belief_state["belief_buckets"] = merge_belief_buckets_update_not_rewrite(
                prev_buckets,
                {},
            )
    belief_after_fingerprint = _belief_fingerprint(belief_state)
    belief_merge_changed = belief_before_fingerprint != belief_after_fingerprint

    if os.getenv("BELIEF_GOVERNOR_ENABLED", "0") == "1":
        world_v2 = world_v1_to_v2(world_state)
        guidance, governor_meta = derive_behavior_guidance(belief_state, world_v2)
        belief_state.setdefault("universal", {})["behavior_guidance"] = guidance
        meta.update({"governor_used": True, **governor_meta})
    else:
        meta.update({"governor_used": False})
    meta.update(
        {
            "allow_health_change": allow_health_change,
            "uni_patch_keys": sorted(list((uni_patch or {}).keys()))[:50],
            "negotiation_patch_keys": sorted(list((neg_patch or {}).keys()))[:50],
            "belief_bucket_patch_keys": sorted(list((belief_buckets_patch or {}).keys()))[:20],
            "belief_issue": "parse_error" if llm_failed else "",
            "belief_error": parse_error_message if llm_failed else "",
            "belief_before_fingerprint": belief_before_fingerprint,
            "belief_after_fingerprint": belief_after_fingerprint,
            "belief_merge_changed": belief_merge_changed,
            "belief_patch_after_normalize": _safe_preview(normalized_buckets_patch),
            "belief_patch_counts": raw_patch_counts,
            "belief_patch_after_normalize_counts": normalized_patch_counts,
            "belief_validation_issues_out": _issues,
            "belief_dropped_fields": belief_dropped_fields,
            "belief_confidence_clamps": {"num_clamped": int(confidence_clamps)},
            "belief_updated_fields": sorted(list(belief_state.keys())),
            "belief_final_top_keys": sorted(list(belief_state.keys())),
            "belief_noop_reason": (
                "parse_error"
                if llm_failed
                else "patch_empty"
                if not (uni_patch or neg_patch or normalized_buckets_patch)
                else "merge_no_effect"
                if not belief_merge_changed
                else ""
            ),
        }
    )

    meta["belief_latency_ms"] = int((time.perf_counter() - started) * 1000)
    return belief_state, meta
