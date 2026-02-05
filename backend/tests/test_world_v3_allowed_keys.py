from negotiation.extractors.world_extractor_v3 import extract_world_patch_llm_v3


class _FakeDeps:
    def __init__(self, payload: str):
        self._payload = payload

    def execute(self, _messages):
        return self._payload


def test_filters_unknown_universal_domain_keys():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{"tone_signal":"friendly","unknown_key":true},'
        '"negotiation_domain_patch":{},"universal_patch":{},"open_claims":[]}'
    )
    u_patch, _n_patch, _u, _claims, _meta = extract_world_patch_llm_v3(
        deps, "hola", {}, {}, "general", 1
    )
    assert u_patch == {"tone_signal": "friendly"}


def test_filters_unknown_negotiation_domain_keys():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{},'
        '"negotiation_domain_patch":{"price_mentioned":true,"weird":1},'
        '"universal_patch":{},"open_claims":[]}'
    )
    _u_patch, n_patch, _u, _claims, _meta = extract_world_patch_llm_v3(
        deps, "hola", {}, {}, "negotiation", 1
    )
    assert n_patch == {"price_mentioned": True}


def test_empties_negotiation_patch_when_not_negotiation():
    deps = _FakeDeps(
        '{"schema_version":"world_extractor_v3",'
        '"universal_domain_patch":{},'
        '"negotiation_domain_patch":{"price_mentioned":true},'
        '"universal_patch":{},"open_claims":[]}'
    )
    _u_patch, n_patch, _u, _claims, _meta = extract_world_patch_llm_v3(
        deps, "hola", {}, {}, "general", 1
    )
    assert n_patch == {}
