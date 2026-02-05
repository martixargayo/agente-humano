from __future__ import annotations

import hashlib
from typing import Any

from ..evidence.registry import get_spec


def _norm_text_for_dedupe(text: str) -> str:
    return (text or "").strip().lower()[:60]


def _dedupe_key(path: str, polarity: str, bucket: Any, norm_text: str) -> str:
    raw = f"{path}|{polarity}|{bucket}|{norm_text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _record_turn_idx(record: dict) -> int:
    return int(((record.get("provenance") or {}).get("turn_idx") or 0))


def _index_init() -> dict[str, dict]:
    return {"latest_by_path": {}, "best_by_path": {}, "recent_by_path": {}}


def _index_upsert(index: dict[str, Any], record: dict, recent_k: int) -> None:
    claim = record.get("claim", {})
    path = claim.get("path")
    if not path:
        return
    latest = index.setdefault("latest_by_path", {})
    best = index.setdefault("best_by_path", {})
    recent = index.setdefault("recent_by_path", {})
    turn_idx = _record_turn_idx(record)
    if path not in latest or turn_idx >= _record_turn_idx(latest[path]):
        latest[path] = record
    if path not in best:
        best[path] = record
    else:
        current = best[path]
        curr_conf = float(current.get("confidence", 0.0))
        next_conf = float(record.get("confidence", 0.0))
        if next_conf > curr_conf or (
            next_conf == curr_conf and turn_idx >= _record_turn_idx(current)
        ):
            best[path] = record
    recent_list = list(recent.get(path, []))
    recent_list.insert(0, record)
    recent_list.sort(key=_record_turn_idx, reverse=True)
    recent[path] = recent_list[:recent_k]


def _rebuild_v2_index(claims: list[dict], recent_k: int) -> dict[str, dict]:
    index = _index_init()
    for record in claims:
        _index_upsert(index, record, recent_k)
    return index


def _make_record_v2(
    *,
    path: str,
    value: Any,
    polarity: str,
    qualifiers: dict | None,
    confidence: float,
    text: str,
    span: tuple[int, int] | None,
    source: str,
    turn_idx: int,
    raw: dict | None,
    unknown_claims: list[dict],
) -> dict | None:
    spec = get_spec(path)
    if not spec:
        unknown_claims.append(
            {
                "path": path,
                "text": (text or "")[:120],
                "source": source,
                "turn_idx": turn_idx,
                "reason": "path_not_registered",
            }
        )
        return None
    try:
        coerced = spec.coerce(value) if value is not None else None
    except Exception:
        unknown_claims.append(
            {
                "path": path,
                "text": (text or "")[:120],
                "source": source,
                "turn_idx": turn_idx,
                "reason": "coerce_failed",
            }
        )
        return None
    qualifiers = qualifiers or {}
    if not isinstance(qualifiers, dict):
        qualifiers = {}
    cleaned_qualifiers = {k: qualifiers[k] for k in qualifiers if k in spec.qualifiers_allowed}
    bucket = spec.bucketize(coerced)
    norm_text = _norm_text_for_dedupe(text)
    return {
        "dedupe_key": _dedupe_key(path, polarity, bucket, norm_text),
        "claim": {
            "path": path,
            "value": coerced,
            "polarity": polarity or "affirm",
            "unit": spec.unit,
            "qualifiers": cleaned_qualifiers,
        },
        "confidence": float(confidence or 0.0),
        "provenance": {
            "text": text or "",
            "span": span,
            "source": source,
            "turn_idx": int(turn_idx),
            "raw": raw,
        },
    }


def _append_record_v2(
    claims: list[dict],
    record: dict,
    window_turns: int,
) -> bool:
    if not record:
        return False
    dedupe_key = record.get("dedupe_key")
    turn_idx = _record_turn_idx(record)
    for item in reversed(claims[-50:]):
        if item.get("dedupe_key") != dedupe_key:
            continue
        prev_turn = _record_turn_idx(item)
        if abs(turn_idx - prev_turn) <= window_turns:
            return False
    claims.append(record)
    return True
