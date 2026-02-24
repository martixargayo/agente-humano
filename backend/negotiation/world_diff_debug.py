from __future__ import annotations

from typing import Iterable

_WORLD_BUCKETS = {"claims", "requests", "offers", "constraints", "interests", "concessions", "context"}


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(v).strip() for v in values if str(v).strip()})


def world_diff_keys_for_debug(*, world_diff: object, world_state: object) -> list[str]:
    meta = {}
    if isinstance(world_state, dict):
        raw_meta = world_state.get("world_state_meta")
        if isinstance(raw_meta, dict):
            meta = raw_meta

    updated_buckets = _sorted_unique(meta.get("updated_buckets") or [])
    if updated_buckets:
        return updated_buckets

    buckets_from_fields: list[str] = []
    for entry in meta.get("updated_fields") or []:
        text = str(entry).strip()
        if not text:
            continue
        if text.startswith("world_buckets."):
            bucket = text.split(".", 1)[1].split(".", 1)[0].strip()
            if bucket:
                buckets_from_fields.append(bucket)
        elif text in _WORLD_BUCKETS:
            buckets_from_fields.append(text)
    parsed = _sorted_unique(buckets_from_fields)
    if parsed:
        return parsed

    if isinstance(world_diff, dict):
        candidates = [k for k in world_diff.keys() if str(k) != "domain"]
        parsed_candidates = _sorted_unique(candidates)
        if parsed_candidates:
            return parsed_candidates
    return []
