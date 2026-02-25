from .executor_prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_PROMPT, EXECUTOR_OUTPUT_SCHEMA


def resolve_render_profiles(render_state: dict):
    del render_state
    return {}, {}, {"max_words": 30, "max_questions": 1}


__all__ = [
    "EXECUTOR_SYSTEM_PROMPT",
    "EXECUTOR_USER_PROMPT",
    "EXECUTOR_OUTPUT_SCHEMA",
    "resolve_render_profiles",
]
