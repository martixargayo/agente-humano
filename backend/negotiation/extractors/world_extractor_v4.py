from __future__ import annotations


def extract_world_v4(*args, **kwargs) -> tuple[dict, dict]:
    del args, kwargs
    return {}, {"extractor_used": False}
