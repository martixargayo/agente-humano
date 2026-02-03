import os

import pytest

from negotiation.world_state_updater import update_world_state
from negotiation.schemas import default_world_state


def test_llm_default_failure_falls_back_regex(monkeypatch):
    monkeypatch.setenv("USE_LLM_EXTRACTOR", "1")
    monkeypatch.setenv("USE_LEGACY_MATCHERS", "1")

    def _boom():
        raise RuntimeError("no llm")

    monkeypatch.setattr(
        "negotiation.world_state_updater._default_world_llm",
        _boom,
    )

    world, meta = update_world_state(
        default_world_state(),
        "precio 9000",
        extractor_mode="llm",
        conversation_mode="negotiation",
    )

    assert meta.get("extractor_failed") is True
    assert meta.get("extractor_used") is False
    assert meta.get("extractor_mode") == "llm"
    assert world.get("world_state_meta", {}).get("last_update_source") == "regex"
