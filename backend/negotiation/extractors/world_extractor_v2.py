from __future__ import annotations

import json

from ..elementos.world_extractor_v2_prompts import (
    WORLD_EXTRACTOR_V2_SYSTEM_PROMPT,
    WORLD_EXTRACTOR_V2_USER_PROMPT,
    ALLOWED_DOMAIN_WORLD_KEYS,
    UNIVERSAL_SPEC,
    OPEN_CLAIMS_SPEC,
    NEGOTIATION_SPEC,
    OUTPUT_SCHEMA,
)


def _safe_json_load(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        s2 = (s or "").strip()
        i = s2.find("{")
        j = s2.rfind("}")
        if i >= 0 and j > i:
            return json.loads(s2[i : j + 1])
        raise


def extract_world_patch_llm_v2(
    deps,
    user_message: str,
    prev_world_state: dict,
    belief_state: dict,
    conversation_mode: str,
    turn_idx: int,
) -> tuple[dict, dict, list, dict]:
    prev_world_state_json = json.dumps(prev_world_state or {}, ensure_ascii=False)
    belief_state_json = json.dumps(belief_state or {}, ensure_ascii=False)

    user_prompt = WORLD_EXTRACTOR_V2_USER_PROMPT.format(
        conversation_mode=conversation_mode,
        user_message=user_message or "",
        prev_world_state_json=prev_world_state_json,
        belief_state_json=belief_state_json,
        output_schema=OUTPUT_SCHEMA.strip(),
        universal_spec=UNIVERSAL_SPEC.strip(),
        open_claims_spec=OPEN_CLAIMS_SPEC.strip(),
        negotiation_spec=NEGOTIATION_SPEC.strip(),
    )

    messages = [
        {"role": "system", "content": WORLD_EXTRACTOR_V2_SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]

    raw = deps.llm.invoke(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")

    data = _safe_json_load(text or "{}")

    schema_version = data.get("schema_version", "")
    if schema_version != "world_extractor_v2":
        raise ValueError(f"extractor_v2 schema_version invalid: {schema_version}")

    domain_patch = dict(data.get("domain_patch") or {})
    universal_patch = dict(data.get("universal_patch") or {})
    open_claims = list(data.get("open_claims") or [])

    allowed = set(ALLOWED_DOMAIN_WORLD_KEYS)
    for k in list(domain_patch.keys()):
        if k not in allowed:
            domain_patch.pop(k, None)

    if conversation_mode != "negotiation":
        domain_patch = {}

    for c in open_claims:
        if isinstance(c, dict):
            c.setdefault("turn_idx", turn_idx)
            c.setdefault("source", "llm")

    meta = {
        "extractor_version": "world_extractor_v2",
        "schema_ok": True,
        "domain_patch_keys": sorted(list(domain_patch.keys()))[:50],
        "open_claims_count": len(open_claims),
    }
    return domain_patch, universal_patch, open_claims, meta
