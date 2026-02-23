# backend/negotiation/world_state_updater.py
from __future__ import annotations

import re
import unicodedata
import copy
import time
from typing import Any, Tuple

from .llm_clients import get_world_llm
from .schemas import WorldState, default_world_state
from .validation import normalize_world_buckets
from .extractors.world_extractor_v4 import extract_world_patch_llm_v4


DEFAULT_ITEM_CONFIDENCE = 0.6

WORLD_BUCKET_KEYS = (
    "offers",
    "concessions",
    "constraints",
    "interests",
    "claims",
    "requests",
    "context",
)


def _flatten_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(key_path)
            paths.update(_flatten_paths(sub, key_path))
        return paths
    if isinstance(value, list):
        for idx, sub in enumerate(value):
            item_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            paths.add(item_path)
            paths.update(_flatten_paths(sub, item_path))
    return paths


def _normalize_text(text: str) -> str:
    txt = str(text or "").lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _bucket_dedupe_key(item: dict) -> str:
    raw_text = _normalize_text(item.get("raw_text", ""))
    if raw_text:
        return raw_text
    return _normalize_text(item.get("text", ""))


def _normalize_bucket_item(raw: object, turn_idx: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "") or "").strip()
    raw_text = str(raw.get("raw_text", "") or "").strip()
    if not text or not raw_text:
        return None

    raw_conf = raw.get("confidence", None)
    explicit_defaulted = raw.get("confidence_defaulted", None)
    confidence_defaulted = bool(explicit_defaulted) if isinstance(explicit_defaulted, bool) else False
    confidence_source = "emitted_by_llm"
    if raw_conf is None:
        confidence = DEFAULT_ITEM_CONFIDENCE
        confidence_defaulted = True
        confidence_source = "defaulted_by_normalizer"
    else:
        try:
            confidence = float(raw_conf)
            if confidence <= 0.0:
                confidence = DEFAULT_ITEM_CONFIDENCE
                confidence_defaulted = True
                confidence_source = "defaulted_by_normalizer"
        except Exception:
            confidence = DEFAULT_ITEM_CONFIDENCE
            confidence_defaulted = True
            confidence_source = "defaulted_by_normalizer"
    confidence = max(0.0, min(1.0, confidence))

    try:
        source_turn = int(raw.get("source_turn", turn_idx) or turn_idx)
    except Exception:
        source_turn = int(turn_idx)
    return {
        "text": text,
        "confidence": confidence,
        "confidence_defaulted": confidence_defaulted,
        "raw_text": raw_text,
        "source_turn": source_turn,
        "confidence_source": confidence_source,
    }


def _sort_bucket_items(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda it: (
            float(it.get("confidence", 0.0) or 0.0),
            int(it.get("source_turn", 0) or 0),
        ),
        reverse=True,
    )


def ensure_world_buckets(world: dict) -> dict:
    buckets = world.get("world_buckets") if isinstance(world.get("world_buckets"), dict) else {}
    out = {}
    for bucket in WORLD_BUCKET_KEYS:
        vals = buckets.get(bucket, []) if isinstance(buckets.get(bucket), list) else []
        out[bucket] = vals
    world["world_buckets"] = out
    return out


def merge_world_buckets_append_mostly(prev_world: dict, patch: dict, turn_idx: int, max_items: int = 8) -> tuple[dict, list[str]]:
    world = copy.deepcopy(prev_world)
    buckets = ensure_world_buckets(world)
    updated: list[str] = []

    for bucket in WORLD_BUCKET_KEYS:
        incoming_raw = patch.get(bucket, []) if isinstance(patch, dict) else []
        incoming_raw = incoming_raw if isinstance(incoming_raw, list) else []
        existing = [
            _normalize_bucket_item(it, turn_idx)
            for it in buckets.get(bucket, [])
        ]
        existing = [it for it in existing if it is not None]
        before_items = _sort_bucket_items(list(existing))[:max_items]
        index = {_bucket_dedupe_key(it): it for it in existing if _bucket_dedupe_key(it)}

        for raw_item in incoming_raw:
            item = _normalize_bucket_item(raw_item, turn_idx)
            if item is None:
                continue
            key = _bucket_dedupe_key(item)
            if not key:
                continue
            if key in index:
                prev = index[key]
                if float(item.get("confidence", 0.0)) > float(prev.get("confidence", 0.0)):
                    index[key] = item
            else:
                index[key] = item

        after = _sort_bucket_items(list(index.values()))[:max_items]
        buckets[bucket] = after
        if after != before_items:
            updated.append(bucket)

    world["world_buckets"] = buckets
    return world, updated


def apply_world_skip_fallback(prev_world: WorldState, user_message: str, turn_count: int | None = None) -> tuple[WorldState, dict]:
    del user_message
    world = dict(prev_world or default_world_state())
    ensure_world_buckets(world)
    world["world_buckets"] = normalize_world_buckets(world.get("world_buckets", {}), default_turn=int((world.get("world_state_meta") or {}).get("turn_idx") or 0), max_items=8)
    issues: list[str] = []
    if turn_count is not None:
        world.setdefault("world_state_meta", {})["turn_idx"] = int(turn_count)
    meta = {
        "extractor_used": False,
        "extractor_skipped": True,
        "fallback_applied": False,
        "fallback_reasons": [],
        "v2_issues": issues,
        "diff_paths": [],
    }
    return world, meta


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


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
    turn_count: int | None = None,
    force_llm: bool = False,
    extractor_mode: str = "llm",
    conversation_mode: str = "general",
    deps: Any | None = None,
    speaker_of_user_message: str = "unknown",
    persona_profile: dict | None = None,
    scene_profile: dict | None = None,
    style_contract: dict | None = None,
    constraints_struct: dict | None = None,
    background_block_public: str = "",
) -> Tuple[WorldState, dict]:
    del recent_history, force_llm, extractor_mode

    base_deepcopy_started = time.perf_counter()
    base = copy.deepcopy(prev_world or default_world_state())
    base_deepcopy_ms = int((time.perf_counter() - base_deepcopy_started) * 1000)
    ensure_world_buckets(base)
    base["world_buckets"] = normalize_world_buckets(base.get("world_buckets", {}), default_turn=int((base.get("world_state_meta") or {}).get("turn_idx") or 0), max_items=8)

    prev_turn_idx = int((base.get("world_state_meta") or {}).get("turn_idx") or 0)
    turn_idx = int(turn_count or 0) if turn_count is not None else 0
    if turn_idx <= 0:
        turn_idx = prev_turn_idx + 1
    elif turn_idx <= prev_turn_idx:
        turn_idx = prev_turn_idx + 1
    base.setdefault("world_state_meta", {})
    base["world_state_meta"]["turn_idx"] = turn_idx
    base["world_state_meta"].setdefault("unknown_claims", [])

    belief_state = belief_state or {}

    if deps is not None and hasattr(deps, "execute") and not hasattr(deps, "llm"):
        llm_deps = deps
    else:
        llm = getattr(deps, "llm", None) if deps is not None else None
        if llm is None:
            llm = _default_world_llm()
        llm_deps = type("Deps", (), {"llm": llm})()

    world_deepcopy_started = time.perf_counter()
    world = copy.deepcopy(base)
    world_deepcopy_ms = int((time.perf_counter() - world_deepcopy_started) * 1000)
    ensure_world_buckets(world)

    timers: dict[str, int] = {
        "world_deepcopy_ms": int(base_deepcopy_ms + world_deepcopy_ms),
        "world_merge_ms": 0,
        "world_normalize_ms": 0,
        "world_diff_paths_ms": 0,
        "world_json_dump_prev_ms": 0,
    }

    try:
        extractor_started = time.perf_counter()
        buckets_patch, extractor_meta = extract_world_patch_llm_v4(
            llm_deps,
            user_message,
            base,
            belief_state,
            conversation_mode,
            turn_idx,
            speaker_of_user_message=speaker_of_user_message,
            persona_profile=persona_profile,
            scene_profile=scene_profile,
            style_contract=style_contract,
            constraints_struct=constraints_struct,
            background_block_public=background_block_public,
        )
        timers["world_json_dump_prev_ms"] = int((extractor_meta or {}).get("world_json_dump_prev_ms", 0) or 0)
        timers["world_extractor_llm_ms"] = int((extractor_meta or {}).get("extractor_llm_latency_ms", 0) or 0)
        timers["world_extractor_total_ms"] = int((time.perf_counter() - extractor_started) * 1000)

        merge_started = time.perf_counter()
        world, updated_buckets = merge_world_buckets_append_mostly(world, buckets_patch, turn_idx=turn_idx, max_items=8)
        timers["world_merge_ms"] = int((time.perf_counter() - merge_started) * 1000)

        normalize_started = time.perf_counter()
        world["world_buckets"] = normalize_world_buckets(world.get("world_buckets", {}), default_turn=turn_idx, max_items=8)
        timers["world_normalize_ms"] = int((time.perf_counter() - normalize_started) * 1000)
        v2_issues: list[str] = []
        world.setdefault("world_state_meta", {})["last_update_source"] = "llm"
        world["world_state_meta"]["error"] = ""
        world["world_state_meta"]["extractor_failed"] = False
        world["world_state_meta"]["updated_fields"] = [f"world_buckets.{bucket}" for bucket in updated_buckets]
        world["world_state_meta"]["updated_buckets"] = updated_buckets

        diff_paths_started = time.perf_counter()
        base_vs_new_diff = diff_world_state(base, world)
        if base_vs_new_diff:
            diff_paths = sorted(_flatten_paths(base_vs_new_diff))
        else:
            diff_paths = []
        timers["world_diff_paths_ms"] = int((time.perf_counter() - diff_paths_started) * 1000)
        meta = {
            **(extractor_meta if isinstance(extractor_meta, dict) else {}),
            "extractor_used": True,
            "extractor_failed": False,
            "v2_issues": v2_issues,
            "updated_buckets": updated_buckets,
            "diff_paths": diff_paths,
            "backstop_reasons": [],
            "rejected_claims": [],
            "timers": timers,
            "prev_world_bytes": int((extractor_meta or {}).get("prev_world_bytes", 0) or 0),
            "world_diff_bytes": len(str(base_vs_new_diff)),
            "extractor_llm_start_ts": (extractor_meta or {}).get("extractor_llm_start_ts", ""),
            "extractor_llm_end_ts": (extractor_meta or {}).get("extractor_llm_end_ts", ""),
            "extractor_llm_model": (extractor_meta or {}).get("extractor_llm_model"),
            "extractor_llm_tokens_in": (extractor_meta or {}).get("extractor_llm_tokens_in"),
            "extractor_llm_tokens_out": (extractor_meta or {}).get("extractor_llm_tokens_out"),
            "extractor_llm_queue_ms": (extractor_meta or {}).get("extractor_llm_queue_ms"),
            "extractor_llm_ttfb_ms": (extractor_meta or {}).get("extractor_llm_ttfb_ms"),
        }
        return world, meta

    except Exception as exc:
        world.setdefault("world_state_meta", {})["last_update_source"] = "llm"
        world["world_state_meta"]["error"] = f"{type(exc).__name__}: {exc}"
        world["world_state_meta"]["extractor_failed"] = True
        ensure_world_buckets(world)
        world["world_buckets"] = normalize_world_buckets(world.get("world_buckets", {}), default_turn=turn_idx, max_items=8)
        v2_issues: list[str] = []
        meta = {
            "extractor_used": True,
            "extractor_failed": True,
            "error": str(exc),
            "v2_issues": v2_issues,
            "updated_buckets": [],
            "backstop_reasons": [],
            "timers": timers,
        }
        return world, meta


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    diff: dict = {}
    domain_diff: dict[str, dict] = {}

    tracked = {"world_buckets", "world_state_meta"}
    for key in tracked:
        if prev.get(key) != new.get(key):
            domain_diff[key] = {"before": prev.get(key), "after": new.get(key)}

    if domain_diff:
        diff["domain"] = domain_diff
    return diff
