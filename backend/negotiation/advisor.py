from __future__ import annotations


def advisor_llm(*args, **kwargs) -> tuple[dict, dict]:
    del args, kwargs
    return {}, {"advisor_disabled": True}
