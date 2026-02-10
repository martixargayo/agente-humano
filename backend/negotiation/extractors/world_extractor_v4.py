from __future__ import annotations

from typing import Tuple

from .world_extractor_v3 import extract_world_patch_llm_v3
from ..world_belief_adapters import world_v1_to_v2


def extract_world_patch_llm_v4(
    deps,
    user_message: str,
    prev_world_state: dict,
    belief_state: dict,
    conversation_mode: str,
    turn_idx: int,
) -> Tuple[dict, dict, dict, list, dict]:
    u_patch, n_patch, universal_patch, open_claims, meta = extract_world_patch_llm_v3(
        deps,
        user_message,
        prev_world_state,
        belief_state,
        conversation_mode,
        turn_idx,
    )
    # ensure this extractor is treated as v4 in metadata while preserving backward compatibility.
    meta = dict(meta)
    meta["extractor_version"] = "world_extractor_v4"
    meta["schema_version"] = "world_extractor_v4"
    _ = world_v1_to_v2({"universal_domain": u_patch, "negotiation": n_patch})
    return u_patch, n_patch, universal_patch, open_claims, meta
