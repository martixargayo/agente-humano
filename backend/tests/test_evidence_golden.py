import os

import pytest

from negotiation.world_state_updater import update_world_state
from negotiation.schemas import default_world_state


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "0")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "1")
    monkeypatch.setenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3")
    monkeypatch.setenv("CONF_TONE_REGEX", "0.45")


def _run(message, prev=None):
    world, _meta = update_world_state(prev or default_world_state(), message, turn_count=1)
    return world


def test_golden_price_numeric():
    world = _run("precio 9000€")
    assert world["price_mentioned"] is True
    assert world["price_value"] == 9000.0
    claim = world["world_observations_v2"]["index"]["best_by_path"]["negotiation.price.offer"]
    assert claim["claim"]["value"] == 9000.0


def test_golden_price_mentioned():
    world = _run("el precio es negociable")
    assert world["price_mentioned"] is True
    assert world["price_value"] is None
    claim = world["world_observations_v2"]["index"]["best_by_path"]["negotiation.price.mentioned"]
    assert claim["claim"]["value"] is True


def test_golden_deadline():
    world = _run("lo necesito mañana")
    assert world["deadline_claimed"] is True
    assert world["deadline_days"] == 1
    claim = world["world_observations_v2"]["index"]["best_by_path"]["negotiation.deadline.days"]
    assert claim["claim"]["value"] == 1


def test_golden_other_buyer():
    world = _run("otro comprador ofrece 10.000€ mañana")
    assert world["other_buyer_claimed"] is True
    assert world["other_buyer_offer_price"] == 10000.0
    claim = world["world_observations_v2"]["index"]["best_by_path"]["negotiation.other_buyer.claimed"]
    assert claim["claim"]["value"] is True


def test_golden_tone():
    world = _run("perfecto, seguimos")
    assert world["tone_signal"] == "friendly"
    claim = world["world_observations_v2"]["index"]["best_by_path"]["negotiation.tone.signal"]
    assert claim["claim"]["value"] == "friendly"


def test_golden_unknown_claims():
    prev = default_world_state()
    prev["evidence_items"] = [
        {"type": "UNKNOWN", "field": "invalid_path", "text": "???", "confidence": 0.8, "source": "manual"}
    ]
    world = _run("hola", prev=prev)
    unknown = (world.get("world_state_meta") or {}).get("unknown_claims", [])
    assert unknown
    assert unknown[-1]["reason"] == "invalid_shape"
