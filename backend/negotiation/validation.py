# backend/negotiation/validation.py
from __future__ import annotations

import hashlib
import os
import re
import warnings
from typing import Dict, Iterable, List, Tuple

from .schemas import (
    BeliefState,
    ConversationMode,
    InteractionHealth,
    IntentState,
    IntentStatus,
    IntentType,
    NegotiationPhase,
    PersonaProfile,
    PolicyDecision,
    PhaseState,
    ProgressState,
    RenderConstraints,
    RenderState,
    RiskPosture,
    SceneProfile,
    StyleContract,
    ToneSignal,
    WorldState,
    default_belief_state,
    default_intent_state,
    default_constraints_struct,
    default_policy_decision,
    default_persona_profile,
    default_progress_state,
    default_render_state,
    default_scene_profile,
    default_style_contract,
    default_world_state,
)
from .specs.world_keys import ALLOWED_NEGOTIATION_DOMAIN_KEYS, ALLOWED_UNIVERSAL_DOMAIN_KEYS
from .elementos.belief.belief_contracts import UNIVERSAL_LIMITS, UNIVERSAL_REASON_KEYS
from .elementos.render.render_contracts import (
    PERSONA_VOICE_REGISTERS,
    STYLE_EMOJI_POLICIES,
    STYLE_FORMATS,
    STYLE_LENGTHS,
)


_ALLOWED_HEALTH: set[InteractionHealth] = {"stable", "tense", "stalled"}
_ALLOWED_RISK: set[RiskPosture] = {"low", "mid", "high"}
_ALLOWED_TONE: set[ToneSignal] = {"neutral", "friendly", "tense"}
_ALLOWED_ESCALATION = {"up", "down", "none"}
_MAX_V2_CLAIMS = int(os.getenv("EVIDENCE_V2_MAX_CLAIMS", "200"))
_MAX_V2_UNKNOWN = int(os.getenv("EVIDENCE_V2_MAX_UNKNOWN", "50"))
BELIEF_LEGACY_KEYS = {
    "dynamics",
    "tom",
    "stance",
    "reasons",
    "hypotheses",
    "hypotheses_structural",
    "hypotheses_observational",
    "evaluations",
}
_ALLOWED_INTENT_STATUS: set[IntentStatus] = {
    "inactive",
    "active",
    "succeeded",
    "abandoned",
    "paused",
}
_ALLOWED_INTENT_TYPES: set[IntentType] = {
    "info_extract",
    "relationship",
    "concession",
    "closing",
    "credibility_check",
}
_ALLOWED_PHASES: set[NegotiationPhase] = {
    "opening",
    "discovery",
    "bargaining",
    "closing",
    "recovery",
}
_ALLOWED_REASON_KEYS = {
    "price_signal",
    "deadline_signal",
    "other_buyer_signal",
    "concession_signal",
    "docs_signal",
    "tone_signal",
}
_ALLOWED_STRUCTURAL_HYPOTHESES = {
    "high_urgency",
    "low_flexibility",
    "high_flexibility",
    "credibility_risk",
    "relationship_risk",
}
_ALLOWED_OBSERVATIONAL_HYPOTHESES = {
    "implicit_acceptance",
    "evasion_detected",
    "looping",
    "deescalation",
    "escalation",
    "soft_commitment",
}
_ALLOWED_EVALUATIONS = {
    "commitment_level",
    "cooperation_level",
    "responsiveness",
}
_STRICT_NORMALIZATION = os.getenv("STRICT_NORMALIZATION") == "1"


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_str_list(values: object, max_items: int | None = None) -> List[str]:
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    if max_items is not None:
        return cleaned[:max_items]
    return cleaned


def _unique_list(values: Iterable[str], max_items: int | None = None) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if max_items is not None and len(result) >= max_items:
            break
    return result


_OPEN_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _clamp01(x: object, default: float = 0.0) -> float:
    try:
        v = float(x)  # type: ignore[arg-type]
    except Exception:
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _trim(value: object, max_len: int) -> str:
    if value is None:
        return ""
    t = str(value).strip()
    if len(t) > max_len:
        t = t[:max_len]
    return t


def normalize_universal_state(u: dict | None) -> dict:
    u = dict(u or {})
    goal = dict(u.get("goal") or {})
    goal_norm = {
        "summary": _trim(goal.get("summary", ""), 120),
        "confidence": _clamp01(goal.get("confidence", 0.0), 0.0),
        "evidence_text": _trim(goal.get("evidence_text", ""), 180),
    }
    if not goal_norm["summary"]:
        goal_norm = {}

    def _norm_list(items, max_n, field_norm):
        out = []
        for it in (items or []):
            try:
                d = field_norm(dict(it or {}))
            except Exception:
                continue
            if d:
                out.append(d)
            if len(out) >= max_n:
                break
        return out

    allowed_kind = {"time", "money", "availability", "logistics", "capability", "rule", "safety", "other"}
    allowed_polarity = {"must", "must_not", "prefer", "avoid"}
    allowed_strength = {"low", "medium", "high"}
    allowed_who = {"user", "agent", "other"}
    allowed_status = {"proposed", "agreed", "cancelled", "done"}
    allowed_entity = {"person", "place", "product", "org", "event", "document", "other"}
    allowed_act = {
        "ask",
        "inform",
        "refuse",
        "accept",
        "offer",
        "counter",
        "stall",
        "repair",
        "threaten",
        "confirm",
    }

    def _norm_constraint(d):
        kind = d.get("kind", "other")
        if kind not in allowed_kind:
            kind = "other"
        polarity = d.get("polarity", "must")
        if polarity not in allowed_polarity:
            polarity = "must"
        return {
            "kind": kind,
            "key": _trim(d.get("key", ""), 48),
            "value": _trim(d.get("value", ""), 120),
            "polarity": polarity,
            "confidence": _clamp01(d.get("confidence", 0.0), 0.0),
            "evidence_text": _trim(d.get("evidence_text", ""), 180),
        }

    def _norm_pref(d):
        strength = d.get("strength", "medium")
        if strength not in allowed_strength:
            strength = "medium"
        return {
            "topic": _trim(d.get("topic", ""), 48),
            "value": _trim(d.get("value", ""), 120),
            "strength": strength,
            "confidence": _clamp01(d.get("confidence", 0.0), 0.0),
            "evidence_text": _trim(d.get("evidence_text", ""), 180),
        }

    def _norm_commit(d):
        who = d.get("who", "other")
        if who not in allowed_who:
            who = "other"
        status = d.get("status", "proposed")
        if status not in allowed_status:
            status = "proposed"
        return {
            "who": who,
            "action": _trim(d.get("action", ""), 120),
            "due": _trim(d.get("due", ""), 60),
            "status": status,
            "confidence": _clamp01(d.get("confidence", 0.0), 0.0),
            "evidence_text": _trim(d.get("evidence_text", ""), 180),
        }

    def _norm_entity(d):
        etype = d.get("type", "other")
        if etype not in allowed_entity:
            etype = "other"
        return {
            "name": _trim(d.get("name", ""), 120),
            "type": etype,
            "role": _trim(d.get("role", ""), 48),
            "confidence": _clamp01(d.get("confidence", 0.0), 0.0),
            "evidence_text": _trim(d.get("evidence_text", ""), 180),
        }

    def _norm_act(d):
        act = d.get("act", "inform")
        if act not in allowed_act:
            act = "inform"
        strength = d.get("strength", "medium")
        if strength not in allowed_strength:
            strength = "medium"
        return {
            "act": act,
            "target": _trim(d.get("target", ""), 48),
            "strength": strength,
            "confidence": _clamp01(d.get("confidence", 0.0), 0.0),
            "evidence_text": _trim(d.get("evidence_text", ""), 180),
        }

    u_norm = {
        "goal": goal_norm,
        "constraints": _norm_list(u.get("constraints"), 10, _norm_constraint),
        "preferences": _norm_list(u.get("preferences"), 10, _norm_pref),
        "commitments": _norm_list(u.get("commitments"), 10, _norm_commit),
        "entities": _norm_list(u.get("entities"), 12, _norm_entity),
        "speech_acts": _norm_list(u.get("speech_acts"), 6, _norm_act),
    }
    return u_norm


def _open_claim_dedupe_key(scope: str, category: str, label: str, evidence_text: str) -> str:
    norm = _trim(evidence_text, 60).lower()
    raw = f"{scope}|{category}|{label}|{norm}"
    return "sha1:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def normalize_open_claims(claims: list | None, max_total: int = 50) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    allowed_scopes = {"universal", "negotiation", "other_domain"}
    allowed_categories = {
        "emotion",
        "social_dynamics",
        "tactic",
        "risk",
        "identity",
        "preference",
        "constraint",
        "context",
        "quality",
        "other",
    }
    for it in (claims or []):
        d = dict(it or {})
        scope = d.get("scope", "universal")
        category = d.get("category", "other")
        if scope not in allowed_scopes or category not in allowed_categories:
            continue
        label = _trim(d.get("label", ""), 32)
        if not _OPEN_LABEL_RE.match(label):
            continue
        evidence = _trim(d.get("evidence_text", ""), 180)
        if not evidence:
            continue
        value = _trim(d.get("value", ""), 160)
        conf = _clamp01(d.get("confidence", 0.0), 0.0)
        turn_idx = int(d.get("turn_idx", 0) or 0)
        source = d.get("source", "llm")

        dk = _open_claim_dedupe_key(scope, category, label, evidence)
        if dk in seen:
            continue
        seen.add(dk)

        out.append(
            {
                "scope": scope,
                "category": category,
                "label": label,
                "value": value,
                "confidence": conf,
                "evidence_text": evidence,
                "turn_idx": turn_idx,
                "source": source,
                "dedupe_key": dk,
            }
        )
        if len(out) >= max_total:
            break
    return out


def normalize_belief_universal(u: dict | None) -> dict:
    u = dict(u or {})
    metrics = dict(u.get("metrics") or {})
    dynamics = dict(u.get("dynamics") or {})
    tom = dict(u.get("tom") or {})
    reasons = dict(u.get("reasons") or {})

    m = {
        "trust": _clamp01(metrics.get("trust", 0.5), 0.5),
        "cooperation": _clamp01(metrics.get("cooperation", 0.5), 0.5),
        "clarity": _clamp01(metrics.get("clarity", 0.5), 0.5),
        "engagement": _clamp01(metrics.get("engagement", 0.5), 0.5),
    }

    health = dynamics.get("interaction_health", "stable")
    if health not in ("stable", "tense", "stalled"):
        health = "stable"
    esc = dynamics.get("escalation", "none")
    if esc not in ("up", "down", "none"):
        esc = "none"
    comm = dynamics.get("commitment", "none")
    if comm not in ("hard", "soft", "none"):
        comm = "none"

    d = {
        "interaction_health": health,
        "escalation": esc,
        "looping": bool(dynamics.get("looping", False)),
        "evasion": bool(dynamics.get("evasion", False)),
        "commitment": comm,
    }

    def _norm_list(xs, max_n):
        out = []
        for x in (xs or []):
            s = _trim(x, UNIVERSAL_LIMITS["tom_item_max_len"])
            if s:
                out.append(s)
            if len(out) >= max_n:
                break
        return out

    t = {
        "other_goals": _norm_list(tom.get("other_goals"), UNIVERSAL_LIMITS["tom_list_max"]),
        "other_tactics": _norm_list(tom.get("other_tactics"), UNIVERSAL_LIMITS["tom_list_max"]),
        "other_belief_about_me": _norm_list(
            tom.get("other_belief_about_me"), UNIVERSAL_LIMITS["tom_list_max"]
        ),
        "confidence": _clamp01(tom.get("confidence", 0.0), 0.0),
    }

    r_out = {}
    for k, v in reasons.items():
        if k not in UNIVERSAL_REASON_KEYS:
            continue
        vv = dict(v or {})
        item = {
            "weight": _clamp01(vv.get("weight", 0.0), 0.0),
            "confidence": _clamp01(vv.get("confidence", 0.0), 0.0),
            "evidence": _trim(
                vv.get("evidence") or vv.get("evidence_text") or "",
                UNIVERSAL_LIMITS["reason_evidence_max_len"],
            ),
        }
        if item["evidence"]:
            r_out[k] = item

    return {"metrics": m, "dynamics": d, "tom": t, "reasons": r_out}

def normalize_world_state(raw: object) -> Tuple[WorldState, List[str]]:
    base = default_world_state()
    defaults = default_world_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("world_state_no_dict")
        return base, issues
    universal_domain = raw.get("universal_domain")
    negotiation = raw.get("negotiation")
    if not isinstance(universal_domain, dict):
        universal_domain = {}
    if not isinstance(negotiation, dict):
        negotiation = {}

    for key in ALLOWED_UNIVERSAL_DOMAIN_KEYS:
        if key in raw and key not in universal_domain:
            universal_domain[key] = raw.get(key)
    for key in ALLOWED_NEGOTIATION_DOMAIN_KEYS:
        if key in raw and key not in negotiation:
            negotiation[key] = raw.get(key)

    base["universal_domain"].update(universal_domain)
    base["negotiation"].update(negotiation)

    base["universal_domain"]["message_is_vague"] = bool(
        universal_domain.get(
            "message_is_vague", defaults["universal_domain"]["message_is_vague"]
        )
    )
    tone_signal = universal_domain.get("tone_signal", defaults["universal_domain"]["tone_signal"])
    if tone_signal not in _ALLOWED_TONE:
        issues.append("tone_signal_invalid")
        tone_signal = defaults["universal_domain"]["tone_signal"]
    base["universal_domain"]["tone_signal"] = tone_signal
    base["universal_domain"]["tone_confidence"] = _clamp(
        _coerce_float(
            universal_domain.get(
                "tone_confidence", defaults["universal_domain"]["tone_confidence"]
            ),
            defaults["universal_domain"]["tone_confidence"],
        )
    )

    base["negotiation"]["price_mentioned"] = bool(
        negotiation.get("price_mentioned", defaults["negotiation"]["price_mentioned"])
    )
    price_value = negotiation.get("price_value", defaults["negotiation"]["price_value"])
    if price_value is None:
        base["negotiation"]["price_value"] = None
    else:
        base["negotiation"]["price_value"] = _coerce_float(price_value, 0.0)

    base["negotiation"]["price_firm"] = bool(
        negotiation.get("price_firm", defaults["negotiation"]["price_firm"])
    )
    base["negotiation"]["price_firm_text"] = str(
        negotiation.get("price_firm_text", defaults["negotiation"]["price_firm_text"])
    ).strip()
    base["negotiation"]["deadline_claimed"] = bool(
        negotiation.get("deadline_claimed", defaults["negotiation"]["deadline_claimed"])
    )
    base["negotiation"]["deadline_text"] = str(
        negotiation.get("deadline_text", defaults["negotiation"]["deadline_text"])
    ).strip()
    deadline_days = negotiation.get("deadline_days", defaults["negotiation"]["deadline_days"])
    if deadline_days is None:
        base["negotiation"]["deadline_days"] = None
    else:
        try:
            base["negotiation"]["deadline_days"] = int(deadline_days)
        except (TypeError, ValueError):
            issues.append("deadline_days_invalid")
            base["negotiation"]["deadline_days"] = None
    base["negotiation"]["deadline_kind"] = str(
        negotiation.get("deadline_kind", defaults["negotiation"]["deadline_kind"])
    ).strip()
    base["negotiation"]["urgency_claimed"] = bool(
        negotiation.get("urgency_claimed", defaults["negotiation"]["urgency_claimed"])
    )
    base["negotiation"]["urgency_text"] = str(
        negotiation.get("urgency_text", defaults["negotiation"]["urgency_text"])
    ).strip()
    base["negotiation"]["urgency_reason"] = str(
        negotiation.get("urgency_reason", defaults["negotiation"]["urgency_reason"])
    ).strip()
    base["negotiation"]["other_buyer_claimed"] = bool(
        negotiation.get(
            "other_buyer_claimed", defaults["negotiation"]["other_buyer_claimed"]
        )
    )
    base["negotiation"]["other_buyer_text"] = str(
        negotiation.get("other_buyer_text", defaults["negotiation"]["other_buyer_text"])
    ).strip()
    other_offer = negotiation.get(
        "other_buyer_offer_price", defaults["negotiation"]["other_buyer_offer_price"]
    )
    if other_offer is None:
        base["negotiation"]["other_buyer_offer_price"] = None
    else:
        base["negotiation"]["other_buyer_offer_price"] = _coerce_float(other_offer, 0.0)
    base["negotiation"]["other_buyer_timing_text"] = str(
        negotiation.get(
            "other_buyer_timing_text", defaults["negotiation"]["other_buyer_timing_text"]
        )
    ).strip()
    base["negotiation"]["concession_made"] = bool(
        negotiation.get("concession_made", defaults["negotiation"]["concession_made"])
    )
    base["negotiation"]["concession_text"] = str(
        negotiation.get("concession_text", defaults["negotiation"]["concession_text"])
    ).strip()
    base["negotiation"]["docs_claimed"] = bool(
        negotiation.get("docs_claimed", defaults["negotiation"]["docs_claimed"])
    )
    base["negotiation"]["docs_types"] = _unique_list(
        _coerce_str_list(negotiation.get("docs_types", []))
    )
    base["negotiation"]["batna_claimed"] = bool(
        negotiation.get("batna_claimed", defaults["negotiation"]["batna_claimed"])
    )
    base["negotiation"]["batna_text"] = str(
        negotiation.get("batna_text", defaults["negotiation"]["batna_text"])
    ).strip()
    base["negotiation"]["min_price_claimed"] = bool(
        negotiation.get("min_price_claimed", defaults["negotiation"]["min_price_claimed"])
    )
    base["negotiation"]["min_price_text"] = str(
        negotiation.get("min_price_text", defaults["negotiation"]["min_price_text"])
    ).strip()
    base["negotiation"]["evidence_offered"] = bool(
        negotiation.get("evidence_offered", defaults["negotiation"]["evidence_offered"])
    )
    base["negotiation"]["evidence_text"] = str(
        negotiation.get("evidence_text", defaults["negotiation"]["evidence_text"])
    ).strip()

    evidence_items = raw.get("evidence_items", [])
    if isinstance(evidence_items, list):
        cleaned = []
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            cleaned.append(item)
            if len(cleaned) >= 50:
                break
        base["evidence_items"] = cleaned
    else:
        issues.append("evidence_items_invalid")

    observations = raw.get("world_observations", {})
    if isinstance(observations, dict):
        raw_fields = observations.get("raw_fields", {})
        if isinstance(raw_fields, dict):
            base["world_observations"]["raw_fields"] = raw_fields
        obs_items = observations.get("evidence_items", [])
        if isinstance(obs_items, list):
            cleaned_obs = []
            for item in obs_items:
                if not isinstance(item, dict):
                    continue
                cleaned_obs.append(item)
                if len(cleaned_obs) >= 50:
                    break
            base["world_observations"]["evidence_items"] = cleaned_obs
        else:
            issues.append("world_observations_items_invalid")
    else:
        issues.append("world_observations_invalid")

    observations_v2 = raw.get("world_observations_v2", {})
    if isinstance(observations_v2, dict):
        claims = observations_v2.get("claims", [])
        cleaned_claims = []
        if isinstance(claims, list):
            for item in claims:
                if not isinstance(item, dict):
                    continue
                claim = item.get("claim", {})
                provenance = item.get("provenance", {})
                if not isinstance(claim, dict) or not isinstance(provenance, dict):
                    continue
                path = claim.get("path")
                text = provenance.get("text")
                confidence = item.get("confidence")
                if not path or not isinstance(path, str) or not text or confidence is None:
                    continue
                claim.setdefault("polarity", "affirm")
                claim.setdefault("qualifiers", {})
                cleaned_claims.append(item)
        if cleaned_claims:
            cleaned_claims.sort(
                key=lambda rec: int((rec.get("provenance") or {}).get("turn_idx") or 0),
                reverse=True,
            )
            cleaned_claims = cleaned_claims[:_MAX_V2_CLAIMS]
        base["world_observations_v2"]["claims"] = cleaned_claims
        index = observations_v2.get("index", {})
        if isinstance(index, dict):
            if index:
                base["world_observations_v2"]["index"] = index
        else:
            issues.append("world_observations_v2_index_invalid")
    else:
        issues.append("world_observations_v2_invalid")

    derived = raw.get("world_derived", {})
    if isinstance(derived, dict):
        fields = derived.get("fields", {})
        if isinstance(fields, dict):
            base["world_derived"]["fields"] = fields
        else:
            issues.append("world_derived_fields_invalid")
    else:
        issues.append("world_derived_invalid")

    world_state_meta = raw.get("world_state_meta", {})
    if isinstance(world_state_meta, dict):
        meta = dict(base["world_state_meta"])
        meta["last_update_source"] = str(
            world_state_meta.get("last_update_source", meta["last_update_source"])
        )
        meta["evidence_confidence_min"] = _clamp(
            _coerce_float(
                world_state_meta.get("evidence_confidence_min", meta["evidence_confidence_min"]),
                meta["evidence_confidence_min"],
            )
        )
        meta["updated_fields"] = _unique_list(
            _coerce_str_list(world_state_meta.get("updated_fields", [])), max_items=40
        )
        meta["error"] = str(world_state_meta.get("error", meta.get("error", "")))[:200]
        meta["extractor_failed"] = bool(
            world_state_meta.get("extractor_failed", meta.get("extractor_failed", False))
        )
        turn_idx = world_state_meta.get("turn_idx", meta.get("turn_idx"))
        if turn_idx is None:
            meta["turn_idx"] = None
        else:
            try:
                meta["turn_idx"] = int(turn_idx)
            except (TypeError, ValueError):
                issues.append("world_state_meta_turn_idx_invalid")
                meta["turn_idx"] = None
        unknown_claims = world_state_meta.get("unknown_claims", meta.get("unknown_claims", []))
        if isinstance(unknown_claims, list):
            meta["unknown_claims"] = unknown_claims[-_MAX_V2_UNKNOWN:]
        else:
            issues.append("world_state_meta_unknown_claims_invalid")
        base["world_state_meta"] = meta
    else:
        issues.append("world_state_meta_invalid")

    base["universal_state"] = normalize_universal_state(raw.get("universal_state"))
    base["open_claims"] = normalize_open_claims(raw.get("open_claims"), max_total=50)

    return base, issues


def normalize_belief_state(
    raw: object,
    previous: BeliefState | None = None,
) -> Tuple[BeliefState, List[str]]:
    base = default_belief_state()
    if previous:
        base.update(previous)
    issues: List[str] = []

    if not isinstance(raw, dict):
        issues.append("belief_state_no_dict")
        return base, issues
    if BELIEF_LEGACY_KEYS.intersection(raw.keys()):
        warnings.warn(
            "belief_state legacy flat keys are deprecated; use belief_state['universal']/['negotiation'] only",
            DeprecationWarning,
            stacklevel=2,
        )

    if "universal" not in raw or not isinstance(raw.get("universal"), dict):
        raw["universal"] = {}
    if "negotiation" not in raw or not isinstance(raw.get("negotiation"), dict):
        raw["negotiation"] = {}

    base["universal"] = normalize_belief_universal(raw.get("universal"))

    neg = dict(raw.get("negotiation") or {})
    if not isinstance(neg.get("stance"), dict):
        neg["stance"] = {}
    if not isinstance(neg.get("reasons"), dict):
        neg["reasons"] = {}
    if not isinstance(neg.get("hypotheses"), list):
        neg["hypotheses"] = []
    if not isinstance(neg.get("hypotheses_structural"), list):
        neg["hypotheses_structural"] = []
    if not isinstance(neg.get("hypotheses_observational"), list):
        neg["hypotheses_observational"] = []
    if not isinstance(neg.get("evaluations"), dict):
        neg["evaluations"] = {}
    if not isinstance(neg.get("tom"), dict):
        neg["tom"] = {}
    base["negotiation"] = neg

    return base, issues


def normalize_policy_decision(
    raw: object,
    allowed_policy_ids: Iterable[str],
) -> Tuple[PolicyDecision, List[str]]:
    base = default_policy_decision()
    issues: List[str] = []
    allowed = set(allowed_policy_ids)

    if not isinstance(raw, dict):
        issues.append("policy_decision_no_dict")
        return base, issues

    policy_id = raw.get("policy_id", "")
    if policy_id not in allowed:
        issues.append("policy_id_invalid")
        return base, issues
    base["policy_id"] = str(policy_id)

    base["reason"] = str(raw.get("reason", base["reason"])).strip()[:180]
    base["micro_goal"] = str(raw.get("micro_goal", base["micro_goal"])).strip()[:140]
    base["why_short"] = str(raw.get("why_short", base["why_short"])).strip()[:140]
    base["inputs_used"] = _unique_list(_coerce_str_list(raw.get("inputs_used", [])), max_items=8)

    risk_posture = raw.get("risk_posture", base["risk_posture"])
    if risk_posture not in _ALLOWED_RISK:
        issues.append("risk_posture_invalid")
        risk_posture = base["risk_posture"]
    base["risk_posture"] = risk_posture

    return base, issues


def _normalize_persona_profile(raw: object) -> Tuple[PersonaProfile, List[str]]:
    base = default_persona_profile()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("persona_profile_no_dict")
        return base, issues
    base["persona_id"] = str(raw.get("persona_id", base["persona_id"]))
    base["role"] = str(raw.get("role", base["role"]))
    voice_register = raw.get("voice_register", base["voice_register"])
    if voice_register not in PERSONA_VOICE_REGISTERS:
        issues.append("persona_voice_register_invalid")
        voice_register = base["voice_register"]
    base["voice_register"] = voice_register
    base["values"] = _unique_list(_coerce_str_list(raw.get("values", base["values"])), max_items=6)
    base["hard_limits"] = _unique_list(
        _coerce_str_list(raw.get("hard_limits", base["hard_limits"])), max_items=8
    )
    base["do"] = _unique_list(_coerce_str_list(raw.get("do", base["do"])), max_items=8)
    base["dont"] = _unique_list(_coerce_str_list(raw.get("dont", base["dont"])), max_items=8)
    base["signature_line"] = str(raw.get("signature_line", base.get("signature_line", ""))).strip()[:140]
    return base, issues


def _normalize_scene_profile(raw: object) -> Tuple[SceneProfile, List[str]]:
    base = default_scene_profile()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("scene_profile_no_dict")
        return base, issues
    base["scene_id"] = str(raw.get("scene_id", base["scene_id"]))
    base["setting"] = str(raw.get("setting", base["setting"]))
    base["macro_goal"] = str(raw.get("macro_goal", base["macro_goal"]))
    base["operational_context"] = _unique_list(
        _coerce_str_list(raw.get("operational_context", base["operational_context"])), max_items=8
    )
    base["disclaimers"] = _unique_list(
        _coerce_str_list(raw.get("disclaimers", base.get("disclaimers", []))), max_items=8
    )
    return base, issues


def _normalize_style_contract(raw: object) -> Tuple[StyleContract, List[str]]:
    base = default_style_contract()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("style_contract_no_dict")
        return base, issues
    base["style_id"] = str(raw.get("style_id", base["style_id"]))
    target_length = raw.get("target_length", base["target_length"])
    if target_length not in STYLE_LENGTHS:
        issues.append("style_target_length_invalid")
        target_length = base["target_length"]
    base["target_length"] = target_length
    fmt = raw.get("format", base["format"])
    if fmt not in STYLE_FORMATS:
        issues.append("style_format_invalid")
        fmt = base["format"]
    base["format"] = fmt
    try:
        max_questions = int(raw.get("max_questions", base["max_questions"]))
        base["max_questions"] = max(0, min(6, max_questions))
    except (TypeError, ValueError):
        issues.append("style_max_questions_invalid")
    emoji_policy = raw.get("emoji_policy", base["emoji_policy"])
    if emoji_policy not in STYLE_EMOJI_POLICIES:
        issues.append("style_emoji_policy_invalid")
        emoji_policy = base["emoji_policy"]
    base["emoji_policy"] = emoji_policy
    base["markdown_allowed"] = bool(raw.get("markdown_allowed", base["markdown_allowed"]))
    try:
        bullets_max = int(raw.get("bullets_max", base.get("bullets_max", 4)))
        base["bullets_max"] = max(0, min(8, bullets_max))
    except (TypeError, ValueError):
        issues.append("style_bullets_max_invalid")
    return base, issues


def _normalize_render_state(raw: object) -> Tuple[RenderState, List[str]]:
    base = default_render_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("render_state_no_dict")
        return base, issues
    base["persona_id"] = str(raw.get("persona_id", base["persona_id"])) or base["persona_id"]
    base["scene_id"] = str(raw.get("scene_id", base["scene_id"])) or base["scene_id"]
    base["style_id"] = str(raw.get("style_id", base["style_id"])) or base["style_id"]
    base["language"] = str(raw.get("language", base["language"])) or base["language"]
    persona_profile = raw.get("persona_profile")
    if isinstance(persona_profile, dict):
        base["persona_profile"] = persona_profile
    scene_profile = raw.get("scene_profile")
    if isinstance(scene_profile, dict):
        base["scene_profile"] = scene_profile
    style_contract = raw.get("style_contract")
    if isinstance(style_contract, dict):
        base["style_contract"] = style_contract
    return base, issues


def _normalize_constraints_struct(raw: object) -> Tuple[RenderConstraints, List[str]]:
    base = default_constraints_struct()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("constraints_struct_no_dict")
        return base, issues
    base["forbid_claims"] = _unique_list(
        _coerce_str_list(raw.get("forbid_claims", base["forbid_claims"])), max_items=8
    )
    base["forbid_formats"] = _unique_list(
        _coerce_str_list(raw.get("forbid_formats", base["forbid_formats"])), max_items=6
    )
    base["disallow_numbers"] = bool(raw.get("disallow_numbers", base["disallow_numbers"]))
    base["require_ask_if_missing"] = _unique_list(
        _coerce_str_list(raw.get("require_ask_if_missing", base["require_ask_if_missing"])),
        max_items=6,
    )
    max_questions = raw.get("max_questions", base.get("max_questions"))
    if max_questions is None:
        base["max_questions"] = None
    else:
        try:
            base["max_questions"] = max(0, min(6, int(max_questions)))
        except (TypeError, ValueError):
            issues.append("constraints_struct_max_questions_invalid")
            base["max_questions"] = base.get("max_questions", 2)
    return base, issues


def normalize_progress_state(raw: object) -> Tuple[ProgressState, List[str]]:
    base = default_progress_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("progress_state_no_dict")
        return base, issues
    if "constraints_struct" in raw and "render_constraints_struct" not in raw:
        warnings.warn(
            "constraints_struct is deprecated; use render_constraints_struct",
            DeprecationWarning,
            stacklevel=2,
        )

    conversation_mode = raw.get("conversation_mode", base.get("conversation_mode", "general"))
    if conversation_mode not in {"general", "negotiation"}:
        issues.append("progress_conversation_mode_invalid")
        conversation_mode = base.get("conversation_mode", "general")
    base["conversation_mode"] = conversation_mode  # type: ignore[assignment]
    try:
        base["mode_confidence"] = _clamp(
            _coerce_float(raw.get("mode_confidence", base.get("mode_confidence", 0.0)), 0.0)
        )
    except (TypeError, ValueError):
        issues.append("progress_mode_confidence_invalid")
    try:
        base["mode_last_switch_turn"] = max(
            0, int(raw.get("mode_last_switch_turn", base.get("mode_last_switch_turn", 0)))
        )
    except (TypeError, ValueError):
        issues.append("progress_mode_last_switch_turn_invalid")
    base["policy_pack_active"] = str(
        raw.get("policy_pack_active", base.get("policy_pack_active", "universal"))
    )
    base["render_state"], render_issues = _normalize_render_state(
        raw.get("render_state", base.get("render_state", {}))
    )
    issues.extend(render_issues)
    base["render_constraints_struct"], constraints_issues = _normalize_constraints_struct(
        raw.get(
            "render_constraints_struct",
            raw.get("constraints_struct", base.get("render_constraints_struct", {})),
        )
    )
    issues.extend(constraints_issues)

    persona_profile_raw = raw.get("persona_profile")
    if isinstance(persona_profile_raw, dict):
        base["render_state"]["persona_profile"] = persona_profile_raw
    scene_profile_raw = raw.get("scene_profile")
    if isinstance(scene_profile_raw, dict):
        base["render_state"]["scene_profile"] = scene_profile_raw
    style_contract_raw = raw.get("style_contract")
    if isinstance(style_contract_raw, dict):
        base["render_state"]["style_contract"] = style_contract_raw

    last_executed_policy_id = raw.get("last_executed_policy_id", raw.get("last_policy_id", ""))
    base["last_executed_policy_id"] = str(
        last_executed_policy_id or base["last_executed_policy_id"]
    )
    last_outcome = raw.get(
        "last_executed_policy_outcome",
        raw.get("last_policy_outcome", base["last_executed_policy_outcome"]),
    )
    if last_outcome not in {"good", "neutral", "bad", ""}:
        issues.append("policy_outcome_invalid")
        last_outcome = base["last_executed_policy_outcome"]
    base["last_executed_policy_outcome"] = last_outcome

    last_chosen_policy_id = raw.get("last_chosen_policy_id", raw.get("last_policy_id", ""))
    base["last_chosen_policy_id"] = str(
        last_chosen_policy_id or base["last_chosen_policy_id"]
    )

    policy_last_outcome = raw.get("policy_last_outcome", {})
    if isinstance(policy_last_outcome, dict):
        sanitized: Dict[str, str] = {}
        for key, value in policy_last_outcome.items():
            if value not in {"good", "neutral", "bad", ""}:
                issues.append(f"policy_last_outcome_invalid:{key}")
                continue
            sanitized[str(key)] = value
        base["policy_last_outcome"] = sanitized
    else:
        issues.append("policy_last_outcome_invalid")

    attempts = raw.get("policy_attempts", {})
    if isinstance(attempts, dict):
        sanitized_attempts: Dict[str, int] = {}
        for key, value in attempts.items():
            try:
                sanitized_attempts[str(key)] = int(value)
            except (TypeError, ValueError):
                issues.append(f"policy_attempts_invalid_value:{key}")
        base["policy_attempts"] = sanitized_attempts
    else:
        issues.append("policy_attempts_invalid")

    base["loop_flags"] = _unique_list(_coerce_str_list(raw.get("loop_flags", [])))
    base["turns_in_same_mode"] = int(raw.get("turns_in_same_mode", base["turns_in_same_mode"]))
    base["intent_state"], intent_issues = normalize_intent_state(raw.get("intent_state", {}))
    issues.extend(intent_issues)
    base["phase_state"], phase_issues = normalize_phase_state(raw.get("phase_state", {}))
    issues.extend(phase_issues)
    base["gate_state"], gate_issues = _normalize_gate_state(raw.get("gate_state", {}))
    issues.extend(gate_issues)

    return base, issues


def _normalize_gate_state(raw: object) -> Tuple[dict, List[str]]:
    base = default_progress_state()["gate_state"]
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("gate_state_no_dict")
        return base, issues
    for key in (
        "last_world_refresh_turn",
        "last_belief_refresh_turn",
        "last_planner_refresh_turn",
        "world_skip_count",
        "belief_skip_count",
        "planner_skip_count",
        "allowed_ids_hash_stable_count",
    ):
        value = raw.get(key, base.get(key))
        try:
            base[key] = max(0, int(value))  # type: ignore[index]
        except (TypeError, ValueError):
            issues.append(f"gate_state_invalid:{key}")
    base["allowed_ids_hash_prev"] = str(
        raw.get("allowed_ids_hash_prev", base.get("allowed_ids_hash_prev", ""))
    )
    base["precedence_signature_prev"] = str(
        raw.get("precedence_signature_prev", base.get("precedence_signature_prev", ""))
    )
    loop_flags = raw.get("loop_flags_prev", [])
    base["loop_flags_prev"] = _unique_list(_coerce_str_list(loop_flags))
    input_shape = raw.get("input_shape_prev", {})
    base["input_shape_prev"] = input_shape if isinstance(input_shape, dict) else {}
    last_interaction = raw.get("last_interaction_signals", {})
    base["last_interaction_signals"] = last_interaction if isinstance(last_interaction, dict) else {}
    interaction_fp = raw.get("interaction_fingerprint_prev", {})
    base["interaction_fingerprint_prev"] = (
        interaction_fp if isinstance(interaction_fp, dict) else {}
    )
    base["prev_user_message"] = str(raw.get("prev_user_message", base.get("prev_user_message", "")))
    base["universal_state_fingerprint_prev"] = str(
        raw.get("universal_state_fingerprint_prev", base.get("universal_state_fingerprint_prev", ""))
    )
    version = raw.get("interaction_fingerprint_version", base.get("interaction_fingerprint_version", 1))
    try:
        base["interaction_fingerprint_version"] = max(1, int(version))
    except (TypeError, ValueError):
        issues.append("gate_state_invalid:interaction_fingerprint_version")
    return base, issues


def normalize_phase_state(raw: object) -> Tuple[PhaseState, List[str]]:
    base = default_progress_state()["phase_state"]
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("phase_state_no_dict")
        return base, issues

    phase = raw.get("phase", base["phase"])
    if phase not in _ALLOWED_PHASES:
        issues.append("phase_invalid")
        phase = "opening"
    base["phase"] = phase

    base["confidence"] = _clamp(
        _coerce_float(raw.get("confidence", base["confidence"]), base["confidence"])
    )

    reasons = _unique_list(_coerce_str_list(raw.get("reasons", []), max_items=8), max_items=8)
    base["reasons"] = reasons

    last_updated_turn = raw.get("last_updated_turn", base["last_updated_turn"])
    try:
        base["last_updated_turn"] = max(0, int(last_updated_turn))
    except (TypeError, ValueError):
        issues.append("phase_last_updated_invalid")
        base["last_updated_turn"] = 0

    return base, issues


def _normalize_slots(raw: object) -> Tuple[dict, List[str]]:
    issues: List[str] = []
    slots = {
        "slots_required": [],
        "slots_optional": [],
        "slots_filled": {},
    }
    if not isinstance(raw, dict):
        issues.append("intent_slots_invalid")
        return slots, issues

    slots["slots_required"] = _unique_list(_coerce_str_list(raw.get("slots_required", [])))
    slots["slots_optional"] = _unique_list(_coerce_str_list(raw.get("slots_optional", [])))

    filled_raw = raw.get("slots_filled", {})
    if isinstance(filled_raw, dict):
        filled: Dict[str, dict] = {}
        for key, value in filled_raw.items():
            if not isinstance(value, dict):
                issues.append(f"intent_slot_invalid:{key}")
                continue
            filled[str(key)] = {
                "value": value.get("value"),
                "evidence": str(value.get("evidence", "")).strip(),
                "confidence": _clamp(_coerce_float(value.get("confidence", 0.5), 0.5)),
            }
        slots["slots_filled"] = filled
    else:
        issues.append("intent_slots_filled_invalid")

    return slots, issues


def _normalize_steps(raw: object) -> Tuple[List[dict], List[str]]:
    issues: List[str] = []
    steps: List[dict] = []
    if not isinstance(raw, list):
        return steps, ["intent_steps_invalid"]

    legacy_map = {
        "ask_open": "probe_open",
        "narrow": "probe_narrow",
        "validate": "request_evidence",
        "leverage": "trade_incentive",
        "deescalate": "pressure_soft",
        "rebuild": "probe_open",
        "advance": "close_next",
        "probe": "probe_open",
        "tradeoff": "trade_incentive",
        "close": "close_next",
        "summarize": "probe_narrow",
        "confirm_terms": "close_next",
        "ask_evidence": "request_evidence",
        "probe_details": "probe_narrow",
    }

    for idx, item in enumerate(raw):
        if isinstance(item, str):
            kind = legacy_map.get(item, "probe_open")
            steps.append(
                {
                    "kind": kind,
                    "target_slot": "unknown",
                    "success_if_filled": ["unknown"],
                }
            )
            issues.append(f"intent_step_legacy:{idx}")
            continue
        if not isinstance(item, dict):
            issues.append(f"intent_step_invalid:{idx}")
            continue
        kind = str(item.get("kind", "")).strip()
        target_slot = str(item.get("target_slot", "")).strip()
        success_if_filled = _unique_list(_coerce_str_list(item.get("success_if_filled", [])))
        if not kind or not target_slot or not success_if_filled:
            issues.append(f"intent_step_missing_fields:{idx}")
            continue
        steps.append(
            {
                "kind": kind,
                "target_slot": target_slot,
                "success_if_filled": success_if_filled,
            }
        )
    return steps[:5], issues


def normalize_intent_state(raw: object) -> Tuple[IntentState, List[str]]:
    base = default_intent_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("intent_state_no_dict")
        return base, issues

    status = raw.get("status", base["status"])
    if status not in _ALLOWED_INTENT_STATUS:
        issues.append("intent_status_invalid")
        status = base["status"]
    base["status"] = status

    intent_type = raw.get("intent_type", base["intent_type"])
    if intent_type not in _ALLOWED_INTENT_TYPES:
        issues.append("intent_type_invalid")
        intent_type = base["intent_type"]
    base["intent_type"] = intent_type

    base["intent_goal"] = str(raw.get("intent_goal", base["intent_goal"])).strip()
    steps, step_issues = _normalize_steps(raw.get("steps", []))
    if step_issues:
        issues.extend(step_issues)
    base["steps"] = steps
    base["step_idx"] = int(raw.get("step_idx", base["step_idx"]))
    base["step_attempts"] = int(raw.get("step_attempts", base["step_attempts"]))
    base["max_attempts_per_step"] = max(
        1, int(raw.get("max_attempts_per_step", base["max_attempts_per_step"]))
    )
    base["success_criteria"] = _unique_list(
        _coerce_str_list(raw.get("success_criteria", []), max_items=5)
    )

    slots, slot_issues = _normalize_slots(raw.get("slots", {}))
    base["slots"] = slots
    issues.extend(slot_issues)

    base["confidence"] = _clamp(_coerce_float(raw.get("confidence", base["confidence"]),
                                              base["confidence"]))
    base["no_progress_turns"] = int(raw.get("no_progress_turns", base["no_progress_turns"]))
    base["slot_fill_count"] = int(raw.get("slot_fill_count", base["slot_fill_count"]))
    base["slot_fill_count_recent"] = int(
        raw.get("slot_fill_count_recent", base["slot_fill_count_recent"])
    )
    base["created_turn"] = int(raw.get("created_turn", base["created_turn"]))
    base["last_turn"] = int(raw.get("last_turn", base["last_turn"]))
    base["continue_until"] = str(raw.get("continue_until", base["continue_until"])).strip()
    base["abandon_reasons"] = _unique_list(_coerce_str_list(raw.get("abandon_reasons", [])))
    base["last_observation"] = str(raw.get("last_observation", base["last_observation"])).strip()
    base["next_action_hint"] = str(raw.get("next_action_hint", base["next_action_hint"])).strip()

    if base["status"] == "active":
        if not base["steps"]:
            issues.append("intent_steps_missing")
        if base["steps"]:
            max_idx = len(base["steps"]) - 1
            if base["step_idx"] < 0 or base["step_idx"] > max_idx:
                issues.append("intent_step_idx_invalid")
                base["step_idx"] = min(max(base["step_idx"], 0), max_idx)
        else:
            base["step_idx"] = 0

    return base, issues
