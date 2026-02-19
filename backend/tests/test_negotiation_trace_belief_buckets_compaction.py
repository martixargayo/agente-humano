from __future__ import annotations

from negotiation.negotiation_graph import _compact_belief_buckets


def test_compact_belief_buckets_keeps_hypotheses_as_dicts():
    state = {
        "belief_buckets": {
            "hypotheses": [
                {"text": "Sacrificio de dinero futuro por dinero hoy.", "confidence": 0.86, "status": "active"}
            ]
        }
    }

    compact = _compact_belief_buckets(state)

    assert isinstance(compact["hypotheses"][0], dict)
    assert compact["hypotheses"][0]["text"].startswith("Sacrificio")


def test_compact_belief_buckets_drops_legacy_repr_strings():
    state = {
        "belief_buckets": {
            "hypotheses": [
                "{'text': 'Sacrificio de dinero futuro por dinero hoy. (0.86)', 'confidence': 0.86, 'status': 'active'}"
            ]
        }
    }

    compact = _compact_belief_buckets(state)

    assert compact["hypotheses"] == []
    assert all("{'text':" not in str(item) for item in compact["hypotheses"])
