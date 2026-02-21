from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Tuple

from ..telemetry.llm_usage import extract_llm_usage

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
  "confidence": 0.85,
  "raw_text": "literal quote from user message",
  "source_turn": {turn_idx}
}

- Append-mostly: propose only NEW items from this user message.
- Do not rewrite prior items.
- If user expresses a conditional/implicit exchange, add at least one item in offers or concessions.
- Keep text simple and concise.
- raw_text is mandatory for every emitted item.
- confidence is mandatory and must be numeric in [0,1].
- Use confidence >= 0.60 for emitted items; if confidence would be < 0.60, do not emit that item.
- Never emit confidence=0 unless the quote explicitly states total uncertainty.
- If no new information for a bucket, return empty list for that bucket.
""".strip()


_BUCKETS = ("offers", "concessions", "constraints", "interests", "claims", "requests", "context")
DEFAULT_ITEM_CONFIDENCE = 0.6


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

    raw_conf = raw.get("confidence", None)
    confidence_defaulted = False
    confidence_source = "emitted_by_llm"
    if raw_conf is None:
        confidence = DEFAULT_ITEM_CONFIDENCE
        confidence_defaulted = True
        confidence_source = "defaulted_by_parser"
    else:
        try:
            confidence = float(raw_conf)
            if confidence <= 0.0:
                confidence = DEFAULT_ITEM_CONFIDENCE
                confidence_defaulted = True
                confidence_source = "defaulted_by_parser"
        except Exception:
            confidence = DEFAULT_ITEM_CONFIDENCE
            confidence_defaulted = True
            confidence_source = "defaulted_by_parser"
    confidence = max(0.0, min(1.0, confidence))

    source_turn = raw.get("source_turn", turn_idx)
    try:
        source_turn = int(source_turn)
    except Exception:
        source_turn = int(turn_idx)
    return {
        "text": text,
        "confidence": confidence,
        "confidence_defaulted": confidence_defaulted,
        "confidence_source": confidence_source,
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
    dump_started = time.perf_counter()
    prev_world_state_json = json.dumps(prev_world_state or {}, ensure_ascii=False)
    json_dump_prev_ms = int((time.perf_counter() - dump_started) * 1000)
    user_prompt = WORLD_EXTRACTOR_V4_USER_PROMPT
    user_prompt = user_prompt.replace("{conversation_mode}", str(conversation_mode))
    user_prompt = user_prompt.replace("{turn_idx}", str(int(turn_idx)))
    user_prompt = user_prompt.replace("{user_message}", user_message or "")
    user_prompt = user_prompt.replace("{prev_world_state_json}", prev_world_state_json)
    messages = [
        {"role": "system", "content": WORLD_EXTRACTOR_V4_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    input_prompt_rendered = "\n\n".join(
        f"[{item.get('role', 'user')}]\n{str(item.get('content', ''))}" for item in messages
    )

    invoke_started_perf = time.perf_counter()
    invoke_started_wall = datetime.now(timezone.utc).isoformat()
    raw = deps.llm.invoke(messages) if hasattr(deps, "llm") else deps.execute(messages)
    invoke_ended_wall = datetime.now(timezone.utc).isoformat()
    invoke_latency_ms = int((time.perf_counter() - invoke_started_perf) * 1000)
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
    total_items = sum(len(items) for items in patch.values())
    defaulted_items = sum(
        1
        for items in patch.values()
        for item in items
        if isinstance(item, dict) and bool(item.get("confidence_defaulted", False))
    )
    meta["confidence_defaulted_count"] = int(defaulted_items)
    meta["confidence_item_count"] = int(total_items)
    confidence_values = [
        float(item.get("confidence", 0.0) or 0.0)
        for items in patch.values()
        for item in items
        if isinstance(item, dict)
    ]
    missing_count = sum(
        1
        for items in patch_raw.values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict) and item.get("confidence", None) is None
    )
    zeros_count = sum(1 for value in confidence_values if float(value) == 0.0)
    per_bucket = {}
    for bucket in _BUCKETS:
        bucket_values = [float(item.get("confidence", 0.0) or 0.0) for item in patch.get(bucket, []) if isinstance(item, dict)]
        per_bucket[bucket] = {
            "count": len(bucket_values),
            "missing_count": sum(
                1
                for item in (patch_raw.get(bucket, []) if isinstance(patch_raw.get(bucket), list) else [])
                if isinstance(item, dict) and item.get("confidence", None) is None
            ),
            "zeros_count": sum(1 for v in bucket_values if v == 0.0),
            "min": min(bucket_values) if bucket_values else None,
            "max": max(bucket_values) if bucket_values else None,
            "avg": (sum(bucket_values) / len(bucket_values)) if bucket_values else None,
        }
    meta["confidence_values_emitted"] = {
        "count": len(confidence_values),
        "min": min(confidence_values) if confidence_values else None,
        "max": max(confidence_values) if confidence_values else None,
        "zeros": zeros_count,
        "missing": missing_count,
    }
    meta["extractor_confidence_summary"] = {
        "emitted_count": len(confidence_values),
        "missing_count": int(missing_count),
        "zeros_count": int(zeros_count),
        "min": min(confidence_values) if confidence_values else None,
        "max": max(confidence_values) if confidence_values else None,
        "avg": (sum(confidence_values) / len(confidence_values)) if confidence_values else None,
        "per_bucket": per_bucket,
    }
    llm_usage = extract_llm_usage(raw)
    meta["extractor_llm_latency_ms"] = int(max(0, invoke_latency_ms))
    meta["extractor_llm_start_ts"] = invoke_started_wall
    meta["extractor_llm_end_ts"] = invoke_ended_wall
    meta["extractor_llm_model"] = llm_usage.get("model")
    meta["extractor_llm_tokens_in"] = llm_usage.get("tokens_in")
    meta["extractor_llm_tokens_out"] = llm_usage.get("tokens_out")
    meta["extractor_llm_queue_ms"] = llm_usage.get("queue_ms")
    meta["extractor_llm_ttfb_ms"] = llm_usage.get("ttfb_ms")
    meta["world_json_dump_prev_ms"] = int(max(0, json_dump_prev_ms))
    meta["prev_world_bytes"] = len(prev_world_state_json.encode("utf-8"))
    meta["extractor_input_payload_raw"] = messages
    meta["extractor_input_prompt_rendered"] = input_prompt_rendered
    meta["extractor_output_text_rendered"] = str(text)
    meta["extractor_output_payload_raw"] = data
    return patch, meta
