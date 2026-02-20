from negotiation.state_migration_v3 import migrate_belief_state_to_v3, migrate_world_state_to_v3


LEGACY_WORLD_KEYS = {
    "universal_domain",
    "negotiation",
    "universal_state",
    "universal_v2",
    "negotiation_v2",
    "open_claims",
    "evidence_items",
    "world_observations",
    "world_observations_v2",
    "world_derived",
}


LEGACY_BELIEF_KEYS = {
    "universal",
    "negotiation",
    "dynamics",
    "tom",
    "stance",
    "reasons",
    "hypotheses",
    "hypotheses_structural",
    "hypotheses_observational",
    "evaluations",
}


def test_migrate_world_state_to_v3_strips_legacy_keys():
    legacy = {
        "schema_version": "v2",
        "negotiation": {"price_mentioned": True, "price_value": 9500, "price_firm_text": "9500"},
        "open_claims": [{"label": "market_demand_uncertainty", "evidence_text": "hay más compradores", "confidence": 0.7, "turn_idx": 2}],
        "world_state_meta": {"turn_idx": 2},
    }
    out = migrate_world_state_to_v3(legacy)
    assert out["schema_version"] == "v3"
    assert "offers" in out["world_buckets"]
    assert all(key not in out for key in LEGACY_WORLD_KEYS)


def test_migrate_belief_state_to_v3_strips_legacy_keys():
    legacy = {
        "schema_version": "v2",
        "hypotheses": ["el vendedor tiene urgencia"],
        "universal": {
            "dynamics": {"interaction_health": "tense"},
            "behavior_guidance": {"conflict_risk": 0.8, "recommended_move": "deescalate"},
        },
    }
    out = migrate_belief_state_to_v3(legacy)
    assert out["schema_version"] == "v3"
    assert out["planner_signals"]["interaction_health"] == "tense"
    assert all(key not in out for key in LEGACY_BELIEF_KEYS)
