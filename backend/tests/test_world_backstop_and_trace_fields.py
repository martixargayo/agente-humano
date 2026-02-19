from negotiation.extractors.world_extractor_v3 import extract_world_patch_llm_v3
from negotiation.schemas import default_world_state
from negotiation.world_state_updater import update_world_state


class _FakeDeps:
    def __init__(self, payload: str):
        self._payload = payload

    def execute(self, _messages):
        return self._payload


def test_trace_meta_contains_dropped_patch_keys():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{"tone_signal":"friendly","alien":1},'
        '"negotiation_domain_patch":{"price_mentioned":true,"weird":1},'
        '"universal_patch":{},"open_claims":[]}'
    )
    _u_patch, _n_patch, _u, _claims, meta = extract_world_patch_llm_v3(
        deps, "hola", {}, {}, "general", 1
    )
    assert meta["dropped_patch_keys"]["universal_domain"] == ["alien"]
    assert meta["dropped_patch_keys"]["negotiation_domain"] == ["weird"]


def test_world_backstop_adds_urgency_and_low_demand_claim_in_general_mode():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{"tone_signal":"neutral"},'
        '"negotiation_domain_patch":{},'
        '"universal_patch":{"goal":{}},"open_claims":[]}'
    )
    prev = default_world_state()
    world, meta = update_world_state(
        prev,
        "me preocupa que nadie quiera comprarlo y quiero venderlo lo antes posible",
        turn_count=1,
        conversation_mode="general",
        deps=deps,
    )
    assert world["negotiation"]["urgency_claimed"] is True
    assert "lo antes posible" in world["negotiation"]["urgency_text"].lower()
    labels = [c.get("label") for c in world.get("open_claims", [])]
    assert "market_demand_uncertainty" in labels
    reasons = meta.get("backstop_reasons") or []
    assert "time_pressure_backstop" in reasons
    assert "market_demand_concern_backstop" in reasons


def test_world_backstop_detects_financial_urgency_with_short_term_phrase():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{"tone_signal":"neutral"},'
        '"negotiation_domain_patch":{},'
        '"universal_patch":{},"open_claims":[]}'
    )
    world, meta = update_world_state(
        default_world_state(),
        "necesito dinero y liquidez a corto plazo",
        turn_count=1,
        conversation_mode="general",
        deps=deps,
    )
    assert world["negotiation"]["urgency_claimed"] is True
    assert world["negotiation"]["urgency_reason"] == "financial_need"
    reasons = meta.get("backstop_reasons") or []
    assert "urgency_financial_backstop" in reasons
