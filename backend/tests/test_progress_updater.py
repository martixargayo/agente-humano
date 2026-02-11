from negotiation.progress_updater import _has_info_delta


def test_has_info_delta_handles_split_world_diff():
    world_diff = {
        "domain": {"price_mentioned": {"before": False, "after": True}},
        "interaction": {"implicit_acceptance": {"before": False, "after": True}},
    }
    assert _has_info_delta(world_diff) is True


def test_has_info_delta_handles_legacy_world_diff():
    world_diff = {"price_mentioned": {"before": False, "after": True}}
    assert _has_info_delta(world_diff) is True


def test_has_info_delta_ignores_interaction_only():
    world_diff = {"interaction": {"implicit_acceptance": {"before": False, "after": True}}}
    assert _has_info_delta(world_diff) is False
