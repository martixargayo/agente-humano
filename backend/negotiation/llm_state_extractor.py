# backend/negotiation/llm_state_extractor.py
from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, TypedDict

from .schemas import BeliefState, WorldState


class ExtractorOutput(TypedDict):
    world_patch: Dict[str, Any]
    belief_patch: Dict[str, Any]
    field_evidence: Dict[str, Dict[str, Any]]
    decisions: Dict[str, Any]
    reasons: List[str]
    schema_version: str


ALLOWED_WORLD_KEYS = set(WorldState.__annotations__.keys())
# P0.1: extractor NO puede modificar BeliefState directamente.
ALLOWED_BELIEF_KEYS: set[str] = set()
CRITICAL_EVIDENCE_FIELDS = {
    "price_mentioned",
    "price_value",
    "price_firm",
    "tone_signal",
    "deadline_claimed",
    "other_buyer_claimed",
    "batna_claimed",
    "urgency_claimed",
    "min_price_claimed",
    "evidence_offered",
    "concession_made",
    "docs_claimed",
    "message_is_vague",
}


def _validate_patch_keys(world_patch: Dict[str, Any], belief_patch: Dict[str, Any]) -> None:
    for key in world_patch.keys():
        if key not in ALLOWED_WORLD_KEYS:
            raise AssertionError(f"extractor_illegal_world_key:{key}")
    # P0.1: belief_patch debe estar vacío
    if belief_patch:
        raise AssertionError("extractor_belief_patch_not_allowed_p0")


def _validate_field_evidence(
    world_patch: Dict[str, Any], field_evidence: Dict[str, Dict[str, Any]]
) -> None:
    for field in CRITICAL_EVIDENCE_FIELDS:
        if field not in world_patch:
            continue
        payload = field_evidence.get(field) or {}
        evidence = str(payload.get("evidence", "")).strip()
        if not evidence:
            raise AssertionError(f"extractor_missing_evidence:{field}")
        confidence = payload.get("confidence", None)
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            raise AssertionError(f"extractor_confidence_invalid:{field}")


def _summarize_confidence(field_evidence: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    confidences = [
        float(payload.get("confidence", 0.0))
        for payload in field_evidence.values()
        if isinstance(payload, dict)
    ]
    if not confidences:
        return {"min": 0.0, "avg": 0.0}
    return {"min": min(confidences), "avg": mean(confidences)}


def validate_extractor_output(output: ExtractorOutput) -> None:
    world_patch = output.get("world_patch", {})
    belief_patch = output.get("belief_patch", {})
    _validate_patch_keys(world_patch, belief_patch)
    field_evidence = output.get("field_evidence", {})
    _validate_field_evidence(world_patch, field_evidence)


def extract_state_patch_llm(
    prev_world: WorldState,
    prev_belief: BeliefState,
    user_message: str,
    recent_history: List[Dict[str, str]],
) -> ExtractorOutput:
    """
    Implementación real: llamada a modelo pequeño con JSON estricto.
    En P0, si no hay LLM disponible en tests, se monkeypatchea.
    """
    del prev_world, prev_belief, user_message, recent_history
    output: ExtractorOutput = {
        "world_patch": {},
        "belief_patch": {},
        "field_evidence": {},
        "decisions": {"should_update_beliefs": False, "message_is_vague": False},
        "reasons": ["not_implemented"],
        "schema_version": "world_v1",
    }
    validate_extractor_output(output)
    return output


def build_extractor_meta(output: ExtractorOutput) -> dict:
    field_evidence = output.get("field_evidence", {}) or {}
    world_patch = output.get("world_patch", {}) or {}
    decisions = output.get("decisions", {}) or {}
    return {
        "extractor_output": output,
        "extractor_used": True,
        "extractor_reasons": output.get("reasons", []),
        "extractor_world_patch_keys": sorted(world_patch.keys()),
        "extractor_confidence_summary": _summarize_confidence(field_evidence),
        "extractor_counts": {
            "patched_fields": len(world_patch),
            "evidence_fields": len(
                [
                    key
                    for key, payload in field_evidence.items()
                    if isinstance(payload, dict) and str(payload.get("evidence", "")).strip()
                ]
            ),
        },
        "decisions": decisions,
        "world_patch": world_patch,
    }
