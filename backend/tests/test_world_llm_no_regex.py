import sys

from negotiation.schemas import default_world_state
from negotiation.world_state_updater import update_world_state


def test_world_llm_failure_does_not_fallback_to_regex(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("llm failed")

    monkeypatch.setattr(
        "negotiation.world_state_updater.extract_world_patch_llm_v4",
        _boom,
    )

    prev_world = default_world_state()
    prev_world["universal_domain"]["tone_signal"] = "friendly"
    prev_world["negotiation"]["price_mentioned"] = True

    assert "negotiation.extractors.world_extractor_regex" not in sys.modules
    world, meta = update_world_state(prev_world, "hola", turn_count=1)

    assert "negotiation.extractors.world_extractor_regex" not in sys.modules
    assert meta["extractor_failed"] is True
    assert world["world_state_meta"]["extractor_failed"] is True
    assert world["universal_domain"] == prev_world["universal_domain"]
    assert world["negotiation"] == prev_world["negotiation"]
