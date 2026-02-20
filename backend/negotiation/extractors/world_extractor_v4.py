from __future__ import annotations

import json
from typing import Tuple

WORLD_EXTRACTOR_V4_SYSTEM_PROMPT = """
You are a strict JSON extractor for negotiation world buckets.
Return ONLY valid JSON.
No markdown. No extra keys.
Do not invent numbers or dates.
""".strip()

WORLD_EXTRACTOR_V4_USER_PROMPT = """
Update WORLD in append-mostly mode.

conversation_mode: {conversation_mode}
turn_idx: {turn_idx}

CURRENT user_message:
{user_message}

PREVIOUS world_state (json):
{prev_world_state_json}

RULES:
- Output ONLY this JSON schema:
{
  "schema_version": "world_extractor_v4",
  "world_buckets_patch": {
    "offers": [item],
    "concessions": [item],
    "constraints": [item],
    "interests": [item],
    "claims": [item],
    "requests": [item],
    "context": [item]
  },
  "meta": {
    "negotiation_signal_detected": true|false,
    "extraction_quality": "high|medium|low"
  }
}

item format:
{
  "text": "short human sentence useful for a planner",
  "confidence": 0.0,
  "raw_text": "literal quote from user message",
  "source_turn": {turn_idx}
}

- Append-mostly: propose only NEW items from this user message.
- Do not rewrite prior items.
- If user expresses a conditional/implicit exchange, add at least one item in offers or concessions.
- Keep text simple and concise.
- raw_text is mandatory for every emitted item.
- If no new information for a bucket, return empty list for that bucket.
""".strip()


_BUCKETS = ("offers", "concessions", "constraints", "interests", "claims", "requests", "context")


def _safe_json_load(text: str) -> dict:
    txt = (text or "").strip()
    i = txt.find("{")
    j = txt.rfind("}")
    if i >= 0 and j > i:
        txt = txt[i : j + 1]
    return json.loads(txt)


def _normalize_item(raw: object, turn_idx: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "") or "").strip()
    raw_text = str(raw.get("raw_text", "") or "").strip()
    if not text or not raw_text:
        return None
    try:
        confidence = float(raw.get("confidence", 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    source_turn = raw.get("source_turn", turn_idx)
    try:
        source_turn = int(source_turn)
    except Exception:
        source_turn = int(turn_idx)
    return {
        "text": text,
        "confidence": confidence,
        "raw_text": raw_text,
        "source_turn": source_turn,
    }


def extract_world_patch_llm_v4(
    deps,
    user_message: str,
    prev_world_state: dict,
    belief_state: dict,
    conversation_mode: str,
    turn_idx: int,
) -> Tuple[dict, dict]:
    del belief_state
    prev_world_state_json = json.dumps(prev_world_state or {}, ensure_ascii=False)
    user_prompt = WORLD_EXTRACTOR_V4_USER_PROMPT
    user_prompt = user_prompt.replace("{conversation_mode}", str(conversation_mode))
    user_prompt = user_prompt.replace("{turn_idx}", str(int(turn_idx)))
    user_prompt = user_prompt.replace("{user_message}", user_message or "")
    user_prompt = user_prompt.replace("{prev_world_state_json}", prev_world_state_json)
    messages = [
        {"role": "system", "content": WORLD_EXTRACTOR_V4_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = deps.llm.invoke(messages) if hasattr(deps, "llm") else deps.execute(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = _safe_json_load(text)

    patch_raw = dict(data.get("world_buckets_patch") or {})

    patch: dict = {bucket: [] for bucket in _BUCKETS}
    for bucket in _BUCKETS:
        vals = patch_raw.get(bucket, [])
        vals = vals if isinstance(vals, list) else []
        normalized = []
        for it in vals:
            norm = _normalize_item(it, turn_idx=turn_idx)
            if norm is not None:
                normalized.append(norm)
        patch[bucket] = normalized

    meta = dict(data.get("meta") or {})
    meta.setdefault("negotiation_signal_detected", False)
    meta.setdefault("extraction_quality", "medium")
    meta["extractor_version"] = "world_extractor_v4"
    meta["schema_version"] = str(data.get("schema_version", ""))
    return patch, meta
