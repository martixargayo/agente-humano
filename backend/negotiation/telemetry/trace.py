from __future__ import annotations

from ..schemas import BeliefState, WorldState


def diff_belief_state(prev: BeliefState, new: BeliefState) -> dict:
    diff: dict = {}
    if prev.get("stance") != new.get("stance"):
        diff["stance"] = {"before": prev.get("stance"), "after": new.get("stance")}
    if prev.get("dynamics") != new.get("dynamics"):
        diff["dynamics"] = {"before": prev.get("dynamics"), "after": new.get("dynamics")}
    if prev.get("reasons") != new.get("reasons"):
        diff["reasons"] = {"before": prev.get("reasons"), "after": new.get("reasons")}
    if prev.get("hypotheses") != new.get("hypotheses"):
        diff["hypotheses"] = {"before": prev.get("hypotheses"), "after": new.get("hypotheses")}
    if prev.get("tom") != new.get("tom"):
        diff["tom"] = {"before": prev.get("tom"), "after": new.get("tom")}
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
