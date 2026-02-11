# backend/negotiation/world_state_updater.py
from __future__ import annotations

from typing import Any, Tuple

from .llm_clients import get_world_llm
from .schemas import WorldState, default_world_state
from .validation import normalize_open_claims, normalize_universal_state, normalize_world_state, normalize_world_state_v2
from .extractors.world_extractor_v4 import extract_world_patch_llm_v4

# Backward-compat alias for tests and legacy monkeypatch hooks.
extract_world_patch_llm_v3 = extract_world_patch_llm_v4
from .world_belief_adapters import world_v1_to_v2


def _default_world_llm():
    return get_world_llm()


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


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
    turn_count: int | None = None,
    force_llm: bool = False,
    extractor_mode: str = "llm",
    conversation_mode: str = "negotiation",
    deps: Any | None = None,
) -> Tuple[WorldState, dict]:
    del recent_history, force_llm, extractor_mode

    base = default_world_state()
    if prev_world:
        base, _ = normalize_world_state(prev_world)
    base = world_v1_to_v2(base)

    turn_idx = int(turn_count or 0) or int((base.get("world_state_meta") or {}).get("turn_idx") or 0) + 1
    base.setdefault("world_state_meta", {})
    base["world_state_meta"]["turn_idx"] = turn_idx
    base["world_state_meta"].setdefault("unknown_claims", [])

    belief_state = belief_state or {}

<<<<<<< HEAD
    if deps is not None and hasattr(deps, "execute") and not hasattr(deps, "llm"):
        llm_deps = deps
    else:
        llm = getattr(deps, "llm", None) if deps is not None else None
        if llm is None:
            llm = _default_world_llm()
        llm_deps = type("Deps", (), {"llm": llm})()

    world = dict(base)
    world.setdefault("universal_domain", {})
    world.setdefault("negotiation", {})
    world.setdefault("world_state_meta", {})

    try:
        u_dom_patch, n_dom_patch, universal_patch, open_claims, v3_meta = extract_world_patch_llm_v4(
            llm_deps,
=======
    if use_llm and (force_llm or _should_call_llm_extractor(user_message, base)):
        output = extract_state_patch_llm(base, belief_state, user_message, recent_history)
        decisions = output.get("decisions", {})
        patch = dict(output.get("world_patch", {}))
        llm_evidence = list(output.get("evidence_items", []))
        field_evidence = output.get("field_evidence", {}) or {}
        if "message_is_vague" in decisions and "message_is_vague" not in patch:
            patch["message_is_vague"] = bool(decisions.get("message_is_vague"))
        output = {**output, "world_patch": patch}
        try:
            validate_extractor_output(output)
        except AssertionError as exc:
            err = str(exc)
            if not (
                err.startswith("extractor_missing_evidence")
                or err.startswith("extractor_confidence_invalid")
            ):
                raise
            patch = {}
            llm_evidence = []
            field_evidence = {}
            output = {
                **output,
                "world_patch": patch,
                "field_evidence": field_evidence,
                "evidence_items": llm_evidence,
                "reasons": list(output.get("reasons", [])) + [f"validation_error:{err}"],
                "decisions": {**decisions, "should_update_beliefs": False},
            }
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
>>>>>>> origin/main
            user_message,
            base,
            belief_state,
            conversation_mode,
            turn_idx,
        )
        world["universal_domain"] = dict(world.get("universal_domain") or {})
        world["negotiation"] = dict(world.get("negotiation") or {})
        world["universal_domain"].update(u_dom_patch)
        world["negotiation"].update(n_dom_patch)

        world["universal_state"] = merge_universal_state(
            world.get("universal_state") or {}, universal_patch
        )
        world["open_claims"] = normalize_open_claims(open_claims, max_total=8)

        if conversation_mode != "negotiation":
            world.setdefault("negotiation_v2", {})
            world["negotiation_v2"] = default_world_state().get("negotiation_v2", {})
        world = world_v1_to_v2(world)
        world, v2_issues = normalize_world_state_v2(world)
        world["world_state_meta"]["last_update_source"] = "llm"
        world["world_state_meta"]["error"] = ""
        world["world_state_meta"]["extractor_failed"] = False
        world["world_state_meta"]["updated_fields"] = sorted(
            list(u_dom_patch.keys()) + list(n_dom_patch.keys())
        )
        meta = {**v3_meta, "extractor_version": "world_extractor_v4", "extractor_used": True, "extractor_failed": False, "v2_issues": v2_issues}
        return world, meta

    except Exception as exc:
        world["world_state_meta"]["last_update_source"] = "llm"
        world["world_state_meta"]["error"] = f"{type(exc).__name__}: {exc}"
        world["world_state_meta"]["extractor_failed"] = True
        world = world_v1_to_v2(world)
        world, v2_issues = normalize_world_state_v2(world)
        meta = {"extractor_used": True, "extractor_failed": True, "error": str(exc), "v2_issues": v2_issues}
        return world, meta


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    diff: dict = {}
    domain_diff: dict[str, dict] = {}

    prev_universal = prev.get("universal_domain", {}) if isinstance(prev.get("universal_domain"), dict) else {}
    new_universal = new.get("universal_domain", {}) if isinstance(new.get("universal_domain"), dict) else {}
    prev_neg = prev.get("negotiation", {}) if isinstance(prev.get("negotiation"), dict) else {}
    new_neg = new.get("negotiation", {}) if isinstance(new.get("negotiation"), dict) else {}

    for key in set(prev_universal.keys()) | set(new_universal.keys()):
        if prev_universal.get(key) != new_universal.get(key):
            domain_diff[key] = {"before": prev_universal.get(key), "after": new_universal.get(key)}

    for key in set(prev_neg.keys()) | set(new_neg.keys()):
        if prev_neg.get(key) != new_neg.get(key):
            domain_diff[key] = {"before": prev_neg.get(key), "after": new_neg.get(key)}

    other_keys = {
        key
        for key in new.keys()
        if key not in {"universal_domain", "negotiation", "world_state_meta"}
    }
    for key in other_keys:
        if prev.get(key) != new.get(key):
            domain_diff[key] = {"before": prev.get(key), "after": new.get(key)}

    if domain_diff:
        diff["domain"] = domain_diff

    return diff
