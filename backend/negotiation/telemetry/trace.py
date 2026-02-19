from __future__ import annotations

from ..schemas import BeliefState, WorldState


def diff_belief_state(prev: BeliefState, new: BeliefState) -> dict:
    diff: dict = {}
    prev_universal = prev.get("universal") or {}
    new_universal = new.get("universal") or {}
    prev_negotiation = prev.get("negotiation") or {}
    new_negotiation = new.get("negotiation") or {}

    if prev_negotiation.get("stance") != new_negotiation.get("stance"):
        diff["stance"] = {
            "before": prev_negotiation.get("stance"),
            "after": new_negotiation.get("stance"),
        }
    if prev_universal.get("dynamics") != new_universal.get("dynamics"):
        diff["dynamics"] = {
            "before": prev_universal.get("dynamics"),
            "after": new_universal.get("dynamics"),
        }
    if prev_negotiation.get("reasons") != new_negotiation.get("reasons"):
        diff["reasons"] = {
            "before": prev_negotiation.get("reasons"),
            "after": new_negotiation.get("reasons"),
        }
    if prev_negotiation.get("hypotheses") != new_negotiation.get("hypotheses"):
        diff["hypotheses"] = {
            "before": prev_negotiation.get("hypotheses"),
            "after": new_negotiation.get("hypotheses"),
        }
    if prev_universal.get("tom") != new_universal.get("tom"):
        diff["tom"] = {
            "before": prev_universal.get("tom"),
            "after": new_universal.get("tom"),
        }
    if (prev.get("belief_buckets") or {}) != (new.get("belief_buckets") or {}):
        diff["belief_buckets"] = {
            "before": prev.get("belief_buckets") or {},
            "after": new.get("belief_buckets") or {},
        }
    return diff


def top_evidence_v2(world_state: WorldState) -> list[dict]:
    claims = (world_state.get("world_observations_v2") or {}).get("claims", []) or []
    top = sorted(
        claims,
        key=lambda rec: (
            float(rec.get("confidence", 0.0)),
            int((rec.get("provenance") or {}).get("turn_idx") or 0),
        ),
        reverse=True,
    )[:5]
    compact = []
    for record in top:
        claim = record.get("claim", {}) or {}
        provenance = record.get("provenance", {}) or {}
        compact.append(
            {
                "path": claim.get("path"),
                "value": claim.get("value"),
                "confidence": record.get("confidence"),
                "turn_idx": provenance.get("turn_idx"),
                "text_prefix": str(provenance.get("text", ""))[:60],
            }
        )
    return compact
