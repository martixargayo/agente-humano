from negotiation.schemas import default_world_state
from negotiation.world_state_updater import update_world_state


def _has_path(world, path: str) -> bool:
    claims = (world.get("world_observations_v2") or {}).get("claims", []) or []
    return any((rec.get("claim") or {}).get("path") == path for rec in claims)


def test_world_state_v2_claims_created_and_deduped(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    monkeypatch.setenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3")
    world = default_world_state()
    for turn in range(1, 6):
        world, _meta = update_world_state(world, "8k negociable", turn_count=turn)
    claims = (world.get("world_observations_v2") or {}).get("claims", []) or []
    assert len(claims) <= 2
    price_claims = [
        c for c in claims if (c.get("claim") or {}).get("path") == "negotiation.price.offer"
    ]
    assert price_claims
    assert {c.get("dedupe_key") for c in price_claims} == {price_claims[0].get("dedupe_key")}
    index = (world.get("world_observations_v2") or {}).get("index", {}) or {}
    recent = (index.get("recent_by_path") or {}).get("negotiation.price.offer", [])
    assert len(recent) <= 3


def test_world_state_v2_equivalence_legacy_flags(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "false")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "true")
    world, _meta = update_world_state(default_world_state(), "8k negociable", turn_count=1)
    assert world["price_mentioned"] is True
    assert world["price_value"] == 8000.0
    assert _has_path(world, "negotiation.price.offer")

    monkeypatch.setenv("EVIDENCE_CONFIDENCE_MIN", "0.6")
    world, _meta = update_world_state(default_world_state(), "no negocio", turn_count=1)
    assert world["price_firm"] is False
    assert _has_path(world, "negotiation.price.firmness")

    world, _meta = update_world_state(default_world_state(), "esta semana lo vemos", turn_count=1)
    assert world["deadline_claimed"] is True
    assert world["deadline_days"] == 7
    assert _has_path(world, "negotiation.deadline.days")

    world, _meta = update_world_state(default_world_state(), "gracias, perfecto", turn_count=1)
    assert world["tone_signal"] == "friendly"
    assert _has_path(world, "negotiation.tone.signal")


def test_world_state_v2_rejects_unknown_paths(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "true")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "false")

    def _fake_extractor(*_args, **_kwargs):
        return {
            "world_patch": {},
            "belief_patch": {},
            "field_evidence": {},
            "decisions": {"should_update_beliefs": False},
            "reasons": ["test"],
            "schema_version": "world_v1",
            "evidence_items": [
                {
                    "type": "PRICE",
                    "field": "foo.bar",
                    "polarity": "affirm",
                    "text": "foo bar",
                    "value": None,
                    "source": "llm",
                    "confidence": 0.7,
                    "turn_idx": 1,
                    "span": None,
                    "raw": {"path": "foo.bar"},
                }
            ],
        }

    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_state_patch_llm", _fake_extractor
    )
    monkeypatch.setattr(
        "negotiation.world_state_updater._should_call_llm_extractor", lambda *_args, **_kwargs: True
    )
    world, _meta = update_world_state(default_world_state(), "test", turn_count=1)
    claims = (world.get("world_observations_v2") or {}).get("claims", []) or []
    assert not claims
    unknown = (world.get("world_state_meta") or {}).get("unknown_claims", [])
    assert unknown
    assert unknown[-1]["reason"] == "path_not_registered"
