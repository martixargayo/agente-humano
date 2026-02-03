from negotiation.validation import normalize_open_claims


def test_open_claim_label_regex_rejects():
    claims = [
        {
            "scope": "universal",
            "category": "other",
            "label": "Bad-Label",
            "value": "x",
            "confidence": 0.5,
            "evidence_text": "evidence",
        }
    ]
    assert normalize_open_claims(claims) == []


def test_open_claim_requires_evidence_text():
    claims = [
        {
            "scope": "universal",
            "category": "other",
            "label": "valid_label",
            "value": "x",
            "confidence": 0.5,
            "evidence_text": "",
        }
    ]
    assert normalize_open_claims(claims) == []


def test_open_claim_dedupe_key_is_backend():
    claims = [
        {
            "scope": "universal",
            "category": "other",
            "label": "valid_label",
            "value": "x",
            "confidence": 0.5,
            "evidence_text": "evidence",
            "dedupe_key": "sha1:fake",
        }
    ]
    out = normalize_open_claims(claims)
    assert out
    assert out[0]["dedupe_key"].startswith("sha1:")
    assert out[0]["dedupe_key"] != "sha1:fake"


def test_open_claims_limit_total_50():
    claims = [
        {
            "scope": "universal",
            "category": "other",
            "label": f"label_{i}",
            "value": "x",
            "confidence": 0.5,
            "evidence_text": f"evidence {i}",
        }
        for i in range(80)
    ]
    out = normalize_open_claims(claims, max_total=50)
    assert len(out) == 50
