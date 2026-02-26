from __future__ import annotations

import hashlib
import json

from .schemas import default_semantic_ledger


def normalize_semantic_ledger(candidate: object, prev: dict | None = None) -> dict:
    base = default_semantic_ledger()
    source = candidate if isinstance(candidate, dict) else {}
    prev_source = prev if isinstance(prev, dict) else {}
    for key in base:
        chosen = source.get(key)
        if not isinstance(chosen, list):
            chosen = prev_source.get(key) if isinstance(prev_source.get(key), list) else []
        base[key] = [str(x).strip()[:180] for x in chosen if str(x).strip()][:6]
    return base


def build_effective_semantic_ledger(progress_state: dict | None, semantic_judge: dict | None) -> dict:
    persisted = normalize_semantic_ledger(
        ((progress_state or {}).get("semantic_ledger") if isinstance(progress_state, dict) else {}),
        None,
    )
    judge_ledger = normalize_semantic_ledger(
        ((semantic_judge or {}).get("semantic_ledger") if isinstance(semantic_judge, dict) else {}),
        persisted,
    )
    return normalize_semantic_ledger(judge_ledger, persisted)


def semantic_ledger_hash(ledger: dict | None) -> str:
    text = json.dumps(ledger if isinstance(ledger, dict) else {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
