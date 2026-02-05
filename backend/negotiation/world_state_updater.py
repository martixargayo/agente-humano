# backend/negotiation/world_state_updater.py
from __future__ import annotations

import os
from typing import Any, Tuple

from langchain_openai import ChatOpenAI

from .elementos.world_definitions import (
    CONF,
    EVIDENCE_V2_MAX_CLAIMS,
    EVIDENCE_V2_MAX_UNKNOWN,
    EVIDENCE_V2_RECENT_K,
)
from .evidence.v2_index import (
    _append_record_v2,
    _index_init,
    _make_record_v2,
    _record_turn_idx,
    _rebuild_v2_index,
)
from .evidence.legacy_bridge import (
    LEGACY_FIELD_TO_PATH,
    PATH_TO_LEGACY,
    _append_evidence,
    _make_evidence,
    _path_for_legacy_item,
    _sync_legacy_evidence_from_v2,
)
from .evidence.derivation import _derive_legacy_from_v2
from .schemas import EvidenceItem, WorldState, default_world_state
from .perception.interaction_signals import (
    _coerce_recent_history,
    extract_interaction_signals,
    _previous_user_message,
)
from .extractors.world_extractor_regex import _legacy_regex_update, _merge_list
from .llm_state_extractor import (
    build_extractor_meta,
    extract_state_patch_llm,
    validate_extractor_output,
)
from .validation import normalize_open_claims, normalize_universal_state
from .extractors.world_extractor_v2 import extract_world_patch_llm_v2


def _default_world_llm():
    model = os.getenv("WORLD_EXTRACTOR_MODEL", os.getenv("WORLD_MODEL", "gpt-4o-mini"))
    temperature = float(os.getenv("WORLD_EXTRACTOR_TEMPERATURE", "0"))
    timeout = int(os.getenv("WORLD_EXTRACTOR_TIMEOUT_S", "20"))
    return ChatOpenAI(model=model, temperature=temperature, timeout=timeout)


def _merge_list_by_key(prev: list[dict], new: list[dict], key_fn, max_n: int) -> list[dict]:
    def _score(d: dict) -> float:
        c = float(d.get("confidence", 0.0) or 0.0)
        ev = str(d.get("evidence_text", "") or "")
        bonus = min(len(ev), 180) / 1000.0
        return c + bonus

    index: dict[str, dict] = {}
    for it in (prev or []):
        try:
            k = key_fn(it)
        except Exception:
            continue
        index[k] = it
    for it in (new or []):
        try:
            k = key_fn(it)
        except Exception:
            continue
        if k not in index:
            index[k] = it
        else:
            if _score(it) >= _score(index[k]):
                index[k] = it
    items = list(index.values())
    items.sort(key=_score, reverse=True)
    return items[:max_n]


def merge_universal_state(prev_u: dict | None, patch_u: dict | None) -> dict:
    prev_u = dict(prev_u or {})
    patch_u = dict(patch_u or {})

    prev_u_n = normalize_universal_state(prev_u)
    patch_u_n = normalize_universal_state(patch_u)

    out = dict(prev_u_n)

    prev_goal = dict(prev_u_n.get("goal") or {})
    patch_goal = dict(patch_u_n.get("goal") or {})
    if patch_goal.get("summary"):
        if (not prev_goal.get("summary")) or (
            float(patch_goal.get("confidence", 0.0))
            >= float(prev_goal.get("confidence", 0.0))
        ):
            out["goal"] = patch_goal

    out["constraints"] = _merge_list_by_key(
        out.get("constraints", []),
        patch_u_n.get("constraints", []),
        lambda d: f"{d.get('kind')}|{d.get('key')}|{d.get('value')}|{d.get('polarity')}",
        10,
    )
    out["preferences"] = _merge_list_by_key(
        out.get("preferences", []),
        patch_u_n.get("preferences", []),
        lambda d: f"{d.get('topic')}|{d.get('value')}|{d.get('strength')}",
        10,
    )
    out["commitments"] = _merge_list_by_key(
        out.get("commitments", []),
        patch_u_n.get("commitments", []),
        lambda d: f"{d.get('who')}|{d.get('action')}|{d.get('due')}|{d.get('status')}",
        10,
    )
    out["entities"] = _merge_list_by_key(
        out.get("entities", []),
        patch_u_n.get("entities", []),
        lambda d: f"{d.get('type')}|{d.get('name')}|{d.get('role')}",
        12,
    )
    out["speech_acts"] = _merge_list_by_key(
        out.get("speech_acts", []),
        patch_u_n.get("speech_acts", []),
        lambda d: f"{d.get('act')}|{d.get('target')}|{d.get('evidence_text')[:40]}",
        6,
    )

    return normalize_universal_state(out)


def _infer_field(item: EvidenceItem) -> str:
    if item.get("field"):
        return str(item.get("field"))
    evidence_type = item.get("type")
    if evidence_type == "PRICE":
        return "price_value" if item.get("value") is not None else "price_mentioned"
    if evidence_type == "DEADLINE":
        return "deadline_days"
    if evidence_type == "FIRMNESS":
        return "price_firm"
    if evidence_type == "URGENCY":
        return "urgency_claimed"
    if evidence_type == "OTHER_BUYER":
        return "other_buyer_claimed"
    if evidence_type == "DOCS":
        return "docs_claimed"
    if evidence_type == "BATNA":
        return "batna_claimed"
    if evidence_type == "CONCESSION":
        return "concession_made"
    if evidence_type == "MIN_PRICE":
        return "min_price_claimed"
    if evidence_type == "EVIDENCE_DOC":
        return "evidence_offered"
    if evidence_type == "TONE":
        return "tone_signal"
    return ""


_FIELD_TO_TYPE: dict[str, str] = {
    "price_value": "PRICE",
    "price_mentioned": "PRICE",
    "deadline_days": "DEADLINE",
    "deadline_claimed": "DEADLINE",
    "deadline_text": "DEADLINE",
    "urgency_claimed": "URGENCY",
    "urgency_reason": "URGENCY",
    "price_firm": "FIRMNESS",
    "other_buyer_claimed": "OTHER_BUYER",
    "docs_claimed": "DOCS",
    "docs_types": "DOCS",
    "batna_claimed": "BATNA",
    "min_price_claimed": "MIN_PRICE",
    "evidence_offered": "EVIDENCE_DOC",
    "concession_made": "CONCESSION",
    "tone_signal": "TONE",
}

def _should_call_llm_extractor(user_message: str, prev_world: WorldState) -> bool:
    text = (user_message or "").strip()
    if len(text) <= 3:
        return False
    if any(ch.isdigit() for ch in text):
        return True
    if "€" in text or "$" in text:
        return True
    if len(text) >= 40:
        return True
    if prev_world.get("other_buyer_claimed") or prev_world.get("deadline_claimed"):
        return True
    return False


def _derive_flags_from_evidence(
    world: WorldState,
    confidence_min: float,
) -> WorldState:
    items = world.get("evidence_items", [])
    if not items:
        return world

    for item in items:
        if not item.get("field"):
            item["field"] = _infer_field(item)
        if not item.get("polarity"):
            item["polarity"] = "affirm"

    observed = world.get("world_observations", {}).get("raw_fields", {})
    defaults = default_world_state()
    tone_min = float(os.getenv("CONF_TONE_MIN", "0.45"))
    derived: dict[str, Any] = {
        "price_mentioned": False,
        "price_value": None,
        "deadline_claimed": False,
        "deadline_text": "",
        "deadline_days": None,
        "deadline_kind": "unknown",
        "urgency_claimed": False,
        "urgency_text": "",
        "urgency_reason": "",
        "other_buyer_claimed": False,
        "other_buyer_text": "",
        "other_buyer_offer_price": None,
        "other_buyer_timing_text": "",
        "concession_made": False,
        "concession_text": "",
        "docs_claimed": False,
        "docs_types": [],
        "min_price_claimed": False,
        "min_price_text": "",
        "price_firm": False,
        "price_firm_text": "",
        "evidence_offered": False,
        "evidence_text": "",
        "batna_claimed": False,
        "batna_text": "",
        "tone_signal": world.get("tone_signal", defaults["tone_signal"]),
        "tone_confidence": float(world.get("tone_confidence", defaults["tone_confidence"]) or 0.0),
    }

    def _pick_best(field: str, conf_min: float) -> EvidenceItem | None:
        candidates = [
            item
            for item in items
            if item.get("field") == field
            and float(item.get("confidence", 0.0)) >= conf_min
            and item.get("polarity", "affirm") == "affirm"
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda it: (
                float(it.get("confidence", 0.0)),
                int(it.get("turn_idx") or -1),
            ),
            reverse=True,
        )
        return candidates[0]

    best_price_value = _pick_best("price_value", CONF["PRICE_NUMERIC"])
    best_price_keyword = _pick_best("price_mentioned", CONF["PRICE_KEYWORD"])
    if best_price_value or best_price_keyword:
        derived["price_mentioned"] = True
        if best_price_value and best_price_value.get("value") is not None:
            derived["price_value"] = float(best_price_value["value"])

    best_deadline = _pick_best("deadline_days", CONF["DEADLINE_WEAK"])
    if best_deadline:
        derived["deadline_claimed"] = True
        derived["deadline_text"] = str(best_deadline.get("text", derived["deadline_text"]))
        if best_deadline.get("value") is not None:
            derived["deadline_days"] = int(best_deadline["value"])
        derived["deadline_kind"] = str(observed.get("deadline_kind", derived["deadline_kind"]))

    best_urgency = _pick_best("urgency_claimed", CONF["URGENCY_STRONG"])
    if best_urgency:
        derived["urgency_claimed"] = True
        derived["urgency_text"] = str(best_urgency.get("text", derived["urgency_text"]))
        derived["urgency_reason"] = str(best_urgency.get("text", derived["urgency_reason"]))[:120]

    best_other = _pick_best("other_buyer_claimed", confidence_min)
    if best_other:
        derived["other_buyer_claimed"] = True
        derived["other_buyer_text"] = str(best_other.get("text", derived["other_buyer_text"]))
        if isinstance(best_other.get("value"), dict):
            derived["other_buyer_offer_price"] = best_other["value"].get("offer_price")
            derived["other_buyer_timing_text"] = best_other["value"].get("timing")
        else:
            derived["other_buyer_offer_price"] = observed.get("other_buyer_offer_price")
            derived["other_buyer_timing_text"] = observed.get("other_buyer_timing_text")

    best_concession = _pick_best("concession_made", confidence_min)
    if best_concession:
        derived["concession_made"] = True
        derived["concession_text"] = str(best_concession.get("text", derived["concession_text"]))

    best_docs = _pick_best("docs_claimed", confidence_min)
    if best_docs:
        derived["docs_claimed"] = True
        if best_docs.get("value"):
            derived["docs_types"] = _merge_list(derived["docs_types"], list(best_docs["value"]))
        elif observed.get("docs_types"):
            derived["docs_types"] = _merge_list(derived["docs_types"], list(observed["docs_types"]))

    best_min_price = _pick_best("min_price_claimed", confidence_min)
    if best_min_price:
        derived["min_price_claimed"] = True
        derived["min_price_text"] = str(best_min_price.get("text", derived["min_price_text"]))

    best_firm = _pick_best("price_firm", CONF["FIRMNESS_STRONG"])
    if best_firm:
        derived["price_firm"] = True
        derived["price_firm_text"] = str(best_firm.get("text", derived["price_firm_text"]))

    best_evidence = _pick_best("evidence_offered", confidence_min)
    if best_evidence:
        derived["evidence_offered"] = True
        derived["evidence_text"] = str(best_evidence.get("text", derived["evidence_text"]))

    best_batna = _pick_best("batna_claimed", confidence_min)
    if best_batna:
        derived["batna_claimed"] = True
        derived["batna_text"] = str(best_batna.get("text", derived["batna_text"]))

    best_tone = _pick_best("tone_signal", tone_min)
    if best_tone:
        derived["tone_signal"] = str(best_tone.get("value", derived["tone_signal"]))
        derived["tone_confidence"] = max(
            float(derived.get("tone_confidence", 0.0)), float(best_tone.get("confidence", 0.0))
        )

    world.update(derived)
    world.setdefault("world_derived", {"fields": {}})
    world["world_derived"]["fields"] = dict(derived)
    world.setdefault("world_observations", {"raw_fields": {}, "evidence_items": []})
    world["world_observations"]["evidence_items"] = list(items)
    return world


def _build_v2_from_evidence(
    evidence_items: list[EvidenceItem],
    claims: list[dict],
    *,
    turn_idx: int,
    unknown_claims: list[dict],
) -> list[dict]:
    window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        path = _path_for_legacy_item(item)
        if not path:
            unknown_claims.append(
                {
                    "path": str(item.get("field") or item.get("type") or ""),
                    "text": str(item.get("text", ""))[:120],
                    "source": item.get("source", "manual"),
                    "turn_idx": turn_idx,
                    "reason": "invalid_shape",
                }
            )
            continue
        text = str(item.get("text", "")).strip()
        confidence = item.get("confidence")
        if not text or confidence is None:
            unknown_claims.append(
                {
                    "path": path,
                    "text": text[:120],
                    "source": item.get("source", "manual"),
                    "turn_idx": turn_idx,
                    "reason": "invalid_shape",
                }
            )
            continue
        value = item.get("value")
        if path in {
            "negotiation.price.mentioned",
            "negotiation.deadline.claimed",
            "negotiation.urgency.claimed",
            "negotiation.other_buyer.claimed",
            "negotiation.concession.made",
            "negotiation.batna.claimed",
            "negotiation.evidence.offered",
        } and value is None:
            value = True
        qualifiers: dict[str, Any] = {}
        if path == "negotiation.other_buyer.claimed" and isinstance(value, dict):
            qualifiers = {
                "offer_price": value.get("offer_price"),
                "timing": value.get("timing"),
            }
            value = True
        record = _make_record_v2(
            path=path,
            value=value,
            polarity=item.get("polarity", "affirm"),
            qualifiers=qualifiers,
            confidence=float(confidence),
            text=text,
            span=item.get("span"),
            source=str(item.get("source", "manual")),
            turn_idx=turn_idx,
            raw=item.get("raw"),
            unknown_claims=unknown_claims,
        )
        if record:
            _append_record_v2(claims, record, window_turns)
    claims.sort(key=_record_turn_idx, reverse=True)
    return claims[:EVIDENCE_V2_MAX_CLAIMS]


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
    turn_count: int | None = None,
    force_llm: bool = False,
    extractor_mode: str = "regex",
    conversation_mode: str = "negotiation",
    deps: Any | None = None,
) -> Tuple[WorldState, dict]:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)

    turn_idx = int(turn_count or 0) or int((base.get("world_state_meta") or {}).get("turn_idx") or 0) + 1
    base.setdefault("world_state_meta", {})
    base["world_state_meta"]["turn_idx"] = turn_idx
    base["world_state_meta"].setdefault("unknown_claims", [])
    base.setdefault(
        "world_observations_v2",
        {"claims": [], "index": _index_init()},
    )

    recent_history = _coerce_recent_history(recent_history)
    belief_state = belief_state or {}
    use_llm = os.getenv("USE_LLM_EXTRACTOR", "true").lower() in {"1", "true", "yes"}
    use_legacy = os.getenv("USE_LEGACY_MATCHERS", "true").lower() in {"1", "true", "yes"}
    confidence_min = float(os.getenv("EVIDENCE_CONFIDENCE_MIN", "0.6"))
    base["world_state_meta"]["evidence_confidence_min"] = confidence_min

    if extractor_mode == "llm" and use_llm:
        llm = None
        if deps is not None:
            llm = getattr(deps, "llm", None)
        try:
            if llm is None:
                llm = _default_world_llm()
            llm_deps = type("Deps", (), {"llm": llm})()
            domain_patch, universal_patch, open_claims, v2_meta = extract_world_patch_llm_v2(
                llm_deps,
                user_message,
                base,
                belief_state,
                conversation_mode,
                turn_idx,
            )
        except Exception as exc:
            if use_legacy:
                world = _legacy_regex_update(base, user_message)
                world["world_state_meta"]["last_update_source"] = "regex"
                world["interaction"] = extract_interaction_signals(
                    user_message,
                    base,
                    recent_history=recent_history,
                    tone_signal=world.get("tone_signal"),
                )
                return world, {
                    "extractor_used": False,
                    "extractor_failed": True,
                    "extractor_error": str(exc)[:300],
                    "extractor_mode": "llm",
                    "extractor_reasons": ["llm_v2_failed_fallback_regex"],
                }
            base["world_state_meta"]["last_update_source"] = "regex"
            base["world_state_meta"]["updated_fields"] = []
            base["interaction"] = extract_interaction_signals(
                user_message,
                base,
                recent_history=recent_history,
                tone_signal=base.get("tone_signal"),
            )
            return base, {
                "extractor_used": False,
                "extractor_failed": True,
                "extractor_error": str(exc)[:300],
                "extractor_mode": "llm",
                "extractor_reasons": ["llm_v2_failed_fallback_base"],
            }
        world = dict(base)
        for key, value in domain_patch.items():
            world[key] = value
        world["universal_state"] = merge_universal_state(
            base.get("universal_state"), universal_patch
        )
        open_claims_new = normalize_open_claims(open_claims, max_total=8)
        world["open_claims"] = normalize_open_claims(
            list(base.get("open_claims", []) or []) + open_claims_new, max_total=50
        )
        world["world_state_meta"]["last_update_source"] = "llm"
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        world["interaction"] = extract_interaction_signals(
            user_message,
            base,
            recent_history=recent_history,
            tone_signal=world.get("tone_signal"),
        )
        v2_meta.update(
            {
                "extractor_used": True,
                "extractor_world_patch_keys": sorted(domain_patch.keys()),
                "extractor_mode": "llm",
            }
        )
        return world, v2_meta

    if use_llm and (force_llm or _should_call_llm_extractor(user_message, base)):
        output = extract_state_patch_llm(base, belief_state, user_message, recent_history)
        decisions = output.get("decisions", {})
        patch = dict(output.get("world_patch", {}))
        llm_evidence = list(output.get("evidence_items", []))
        field_evidence = output.get("field_evidence", {}) or {}
        if "message_is_vague" in decisions and "message_is_vague" not in patch:
            patch["message_is_vague"] = bool(decisions.get("message_is_vague"))
        output = {**output, "world_patch": patch}
        validate_extractor_output(output)
        world = dict(base)
        for key, value in patch.items():
            world[key] = value
        generated_items: list[EvidenceItem] = []
        for field, payload in field_evidence.items():
            if not isinstance(payload, dict):
                continue
            evidence_text = str(payload.get("evidence", "")).strip()
            if not evidence_text:
                continue
            confidence = float(payload.get("confidence", confidence_min))
            evidence_type = _FIELD_TO_TYPE.get(field, "")
            if not evidence_type:
                continue
            value = patch.get(field)
            generated_items.append(
                _make_evidence(
                    evidence_type,
                    field,
                    evidence_text,
                    value,
                    "llm",
                    confidence,
                    int(base.get("world_state_meta", {}).get("turn_idx", 0) or 0),
                    raw={"field_evidence": payload},
                )
            )
        if llm_evidence or generated_items:
            window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
            items: list[EvidenceItem] = list(base.get("evidence_items", []) or [])
            for item in llm_evidence or []:
                if isinstance(item, dict):
                    _append_evidence(items, item, window_turns)
            for item in generated_items:
                _append_evidence(items, item, window_turns)
            world["evidence_items"] = items
            world["world_state_meta"]["last_update_source"] = "llm"
        meta = build_extractor_meta(output)
        meta["extractor_mode"] = "llm"
        unknown_claims = list(base.get("world_state_meta", {}).get("unknown_claims", []))
        claims = list((base.get("world_observations_v2") or {}).get("claims", []) or [])
        claims = _build_v2_from_evidence(
            list(world.get("evidence_items", []) or []),
            claims,
            turn_idx=turn_idx,
            unknown_claims=unknown_claims,
        )
        unknown_claims = unknown_claims[-EVIDENCE_V2_MAX_UNKNOWN:]
        world["world_state_meta"]["unknown_claims"] = unknown_claims
        world.setdefault("world_observations_v2", {"claims": [], "index": _index_init()})
        world["world_observations_v2"]["claims"] = claims
        world["world_observations_v2"]["index"] = _rebuild_v2_index(claims, EVIDENCE_V2_RECENT_K)
        world = _sync_legacy_evidence_from_v2(world)
        world = _derive_legacy_from_v2(world, confidence_min)
        world.setdefault("world_observations", {"raw_fields": {}, "evidence_items": []})
        if isinstance(world["world_observations"].get("raw_fields"), dict):
            world["world_observations"]["raw_fields"].update(patch)
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        world["interaction"] = extract_interaction_signals(
            user_message,
            base,
            recent_history=recent_history,
            tone_signal=world.get("tone_signal"),
        )
        return world, meta

    if use_legacy:
        world = _legacy_regex_update(base, user_message)
        world["world_state_meta"]["last_update_source"] = "regex"
        unknown_claims = list(base.get("world_state_meta", {}).get("unknown_claims", []))
        claims = list((base.get("world_observations_v2") or {}).get("claims", []) or [])
        claims = _build_v2_from_evidence(
            list(world.get("evidence_items", []) or []),
            claims,
            turn_idx=turn_idx,
            unknown_claims=unknown_claims,
        )
        unknown_claims = unknown_claims[-EVIDENCE_V2_MAX_UNKNOWN:]
        world["world_state_meta"]["unknown_claims"] = unknown_claims
        world.setdefault("world_observations_v2", {"claims": [], "index": _index_init()})
        world["world_observations_v2"]["claims"] = claims
        world["world_observations_v2"]["index"] = _rebuild_v2_index(claims, EVIDENCE_V2_RECENT_K)
        world = _sync_legacy_evidence_from_v2(world)
        world = _derive_legacy_from_v2(world, confidence_min)
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        world["interaction"] = extract_interaction_signals(
            user_message,
            base,
            recent_history=recent_history,
            tone_signal=world.get("tone_signal"),
        )
        return world, {
            "extractor_used": False,
            "extractor_reasons": ["legacy_fallback"],
            "extractor_world_patch_keys": [],
            "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
            "extractor_mode": "regex",
        }

    base["world_observations_v2"]["index"] = _rebuild_v2_index(
        list((base.get("world_observations_v2") or {}).get("claims", []) or []),
        EVIDENCE_V2_RECENT_K,
    )
    base["world_state_meta"]["unknown_claims"] = list(
        base.get("world_state_meta", {}).get("unknown_claims", [])
    )[-EVIDENCE_V2_MAX_UNKNOWN:]
    base = _sync_legacy_evidence_from_v2(base)
    base = _derive_legacy_from_v2(base, confidence_min)
    base["interaction"] = extract_interaction_signals(
        user_message,
        base,
        recent_history=recent_history,
        tone_signal=base.get("tone_signal"),
    )
    return base, {
        "extractor_used": False,
        "extractor_reasons": ["skipped"],
        "extractor_world_patch_keys": [],
        "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
        "extractor_mode": "none",
    }


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    domain_diff = {
        key: {"before": prev.get(key), "after": new.get(key)}
        for key in new.keys()
        if key != "interaction" and prev.get(key) != new.get(key)
    }
    prev_interaction = prev.get("interaction", {}) if isinstance(prev.get("interaction"), dict) else {}
    new_interaction = new.get("interaction", {}) if isinstance(new.get("interaction"), dict) else {}
    interaction_diff = {
        key: {"before": prev_interaction.get(key), "after": new_interaction.get(key)}
        for key in new_interaction.keys()
        if prev_interaction.get(key) != new_interaction.get(key)
    }
    if not domain_diff and not interaction_diff:
        return {}
    diff: dict = {}
    if domain_diff:
        diff["domain"] = domain_diff
    if interaction_diff:
        diff["interaction"] = interaction_diff
    return diff
