from __future__ import annotations

import json
from typing import Any, Tuple

from ..specs.world_keys import (
    ALLOWED_UNIVERSAL_DOMAIN_KEYS,
    ALLOWED_NEGOTIATION_DOMAIN_KEYS,
)
from ..elementos.world_extractor_v3_prompts import (
    WORLD_EXTRACTOR_V3_SYSTEM_PROMPT,
    WORLD_EXTRACTOR_V3_USER_PROMPT,
    OUTPUT_SCHEMA,
    UNIVERSAL_SPEC,
    OPEN_CLAIMS_SPEC,
    UNIVERSAL_DOMAIN_SPEC,
    NEGOTIATION_DOMAIN_SPEC,
)


def _safe_json_load(text: str) -> dict:
    return json.loads(text)


def extract_world_patch_llm_v3(
    deps,
    user_message: str,
    prev_world_state: dict,
    belief_state: dict,
    conversation_mode: str,
    turn_idx: int,
) -> Tuple[dict, dict, dict, list, dict]:
    """
    Returns:
      universal_domain_patch, negotiation_domain_patch, universal_patch, open_claims, meta
    """
    prev_world_state_json = json.dumps(prev_world_state or {}, ensure_ascii=False)
    belief_state_json = json.dumps(belief_state or {}, ensure_ascii=False)

    user_prompt = WORLD_EXTRACTOR_V3_USER_PROMPT
    replacements = {
        "{conversation_mode}": conversation_mode,
        "{user_message}": user_message or "",
        "{prev_world_state_json}": prev_world_state_json,
        "{belief_state_json}": belief_state_json,
    }
    for key, value in replacements.items():
        user_prompt = user_prompt.replace(key, value)

    messages = [
        {"role": "system", "content": WORLD_EXTRACTOR_V3_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = deps.llm.invoke(messages) if hasattr(deps, "llm") else deps.execute(messages)
    text = raw if isinstance(raw, str) else getattr(raw, "content", "")
    data = _safe_json_load(text)

    u_patch = dict(data.get("universal_domain_patch") or {})
    n_patch = dict(data.get("negotiation_domain_patch") or {})
    universal_patch = dict(data.get("universal_patch") or {})
    open_claims = list(data.get("open_claims") or [])

    u_allowed = set(ALLOWED_UNIVERSAL_DOMAIN_KEYS)
    for k in list(u_patch.keys()):
        if k not in u_allowed:
            u_patch.pop(k, None)

    n_allowed = set(ALLOWED_NEGOTIATION_DOMAIN_KEYS)
    for k in list(n_patch.keys()):
        if k not in n_allowed:
            n_patch.pop(k, None)

    if conversation_mode != "negotiation":
        n_patch = {}

    meta = {
        "extractor_version": "world_extractor_v3",
        "schema_version": str(data.get("schema_version", "")),
        "turn_idx": turn_idx,
        "schema": OUTPUT_SCHEMA,
        "universal_spec": UNIVERSAL_SPEC,
        "open_claims_spec": OPEN_CLAIMS_SPEC,
        "universal_domain_spec": UNIVERSAL_DOMAIN_SPEC,
        "negotiation_domain_spec": NEGOTIATION_DOMAIN_SPEC,
    }
    return u_patch, n_patch, universal_patch, open_claims, meta
