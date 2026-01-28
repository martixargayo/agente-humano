from negotiation.world_state_updater import update_world_state
from negotiation.schemas import default_world_state


def test_deadline_days_without_urgency(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    world, _meta = update_world_state(default_world_state(), "esta semana lo vemos")
    assert world["deadline_claimed"] is True
    assert world["deadline_days"] == 7
    assert world["urgency_claimed"] is False
    assert any(item["type"] == "DEADLINE" for item in world["evidence_items"])


def test_firmness_low_confidence_does_not_force_price_firm(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setenv("EVIDENCE_CONFIDENCE_MIN", "0.6")
    world, _meta = update_world_state(default_world_state(), "no negocio")
    assert world["price_firm"] is False
    assert any(item["type"] == "FIRMNESS" for item in world["evidence_items"])


def test_price_evidence_numeric_value(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    world, _meta = update_world_state(default_world_state(), "8k negociable")
    assert world["price_mentioned"] is True
    assert world["price_value"] == 8000.0
    assert any(item["type"] == "PRICE" for item in world["evidence_items"])


def test_evidence_dedup_window(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3")
    first, _ = update_world_state(default_world_state(), "precio 9000", turn_count=1)
    second, _ = update_world_state(first, "precio 9000", turn_count=2)
    assert len(first["evidence_items"]) == len(second["evidence_items"])
