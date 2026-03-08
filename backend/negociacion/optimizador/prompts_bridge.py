from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_FILES = {
    "memory": "summarizer_prompt.txt",
    "phase_classifier": "phase_classifier_prompt.txt",
    "planner": "planner_prompt.txt",
    "executor": "executor_prompt.txt",
}


def list_prompts() -> list[dict[str, str]]:
    prompts: list[dict[str, str]] = []
    for node, file_name in PROMPT_FILES.items():
        path = PROMPTS_DIR / file_name
        prompts.append(
            {
                "node": node,
                "file": str(path),
                "base_text": path.read_text(encoding="utf-8") if path.exists() else "",
                "prompt_version": f"{node}_base",
            }
        )
    return prompts
