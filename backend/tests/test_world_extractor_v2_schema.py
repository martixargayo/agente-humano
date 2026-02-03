import json

from negotiation.world_state_updater import extract_world_patch_llm_v2, update_world_state
from negotiation.schemas import default_world_state


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    def invoke(self, messages):
        del messages
        return json.dumps(self.payload, ensure_ascii=False)


class _Deps:
    def __init__(self, payload: dict):
        self.llm = _FakeLLM(payload)


def test_domain_patch_keys_filtered():
    payload = {
        "schema_version": "world_extractor_v2",
        "domain_patch": {"price_mentioned": True, "hacker_field": "nope"},
        "universal_patch": {},
        "open_claims": [],
    }
    deps = _Deps(payload)
    domain_patch, _universal_patch, _open_claims, _meta = extract_world_patch_llm_v2(
        deps,
        user_message="ok",
        prev_world_state={"price_mentioned": False},
        belief_state={},
        conversation_mode="negotiation",
        turn_idx=1,
    )
    assert "hacker_field" not in domain_patch
    assert domain_patch.get("price_mentioned") is True


def test_domain_patch_empty_when_general():
    payload = {
        "schema_version": "world_extractor_v2",
        "domain_patch": {"price_mentioned": True},
        "universal_patch": {},
        "open_claims": [],
    }
    deps = _Deps(payload)
    domain_patch, _universal_patch, _open_claims, _meta = extract_world_patch_llm_v2(
        deps,
        user_message="ok",
        prev_world_state={},
        belief_state={},
        conversation_mode="general",
        turn_idx=1,
    )
    assert domain_patch == {}


def test_open_claims_per_turn_cap_8():
    claims = [
        {
            "scope": "universal",
            "category": "context",
            "label": f"label_{i}",
            "value": "x",
            "confidence": 0.5,
            "evidence_text": f"evidence {i}",
        }
        for i in range(20)
    ]
    payload = {
        "schema_version": "world_extractor_v2",
        "domain_patch": {},
        "universal_patch": {},
        "open_claims": claims,
    }
    deps = _Deps(payload)
    world, _meta = update_world_state(
        default_world_state(),
        "ok",
        extractor_mode="llm",
        deps=deps,
        conversation_mode="negotiation",
    )
    assert len(world.get("open_claims", [])) <= 8
    assert len(world.get("open_claims", [])) <= 50
