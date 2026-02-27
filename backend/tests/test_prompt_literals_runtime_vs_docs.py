import re
from pathlib import Path

from prompts import (
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_PROMPT,
    PLANNER_SEMANTIC_V1_SYSTEM_PROMPT,
    PLANNER_SEMANTIC_V1_USER_PROMPT,
)
from negotiation.elementos.render.executor_prompts import (
    EXECUTOR_V2_SYSTEM_PROMPT,
    EXECUTOR_V2_USER_PROMPT,
    EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT,
    EXECUTOR_FINALIZER_V1_USER_PROMPT,
)


def _extract(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'"""\n?(.*?)\n?"""', text, flags=re.S)
    return m.group(1) if m else text.rstrip("\n")


def test_runtime_prompt_literals_match_docs_byte_identical():
    repo = Path(__file__).resolve().parents[2]
    docs = repo / "docs" / "prompts_literal_v2"

    checks = [
        (SUMMARY_SYSTEM_PROMPT, _extract(docs / "SUMMARY_SYSTEM_PROMPT_v2.txt")),
        (SUMMARY_USER_PROMPT, _extract(docs / "SUMMARY_USER_PROMPT_v2.txt")),
        (PLANNER_SEMANTIC_V1_SYSTEM_PROMPT, _extract(docs / "PLANNER_SEMANTIC_V2_SYSTEM_PROMPT.txt")),
        (PLANNER_SEMANTIC_V1_USER_PROMPT, _extract(docs / "PLANNER_SEMANTIC_V2_USER_PROMPT.txt")),
        (EXECUTOR_V2_SYSTEM_PROMPT, _extract(docs / "EXECUTOR_V2_SYSTEM_PROMPT.txt")),
        (EXECUTOR_V2_USER_PROMPT, _extract(docs / "EXECUTOR_V2_USER_PROMPT.txt")),
        (EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT, _extract(docs / "EXECUTOR_FINALIZER_V1_SYSTEM_PROMPT.txt")),
        (EXECUTOR_FINALIZER_V1_USER_PROMPT, _extract(docs / "EXECUTOR_FINALIZER_V1_USER_PROMPT.txt")),
    ]

    for runtime_text, docs_text in checks:
        assert runtime_text == docs_text
