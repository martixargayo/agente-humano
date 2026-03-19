from __future__ import annotations

from pathlib import Path

from ..contexts import resolve_default_negotiation_context, resolve_negotiation_context

PROMPT_FILES = {
    "memory": "summarizer_prompt.txt",
    "phase_classifier": "phase_classifier_prompt.txt",
    "planner": "planner_prompt.txt",
    "executor": "executor_prompt.txt",
}


def _prompts_dir_for_context(context_id: str | None = None) -> Path:
    resolved = resolve_negotiation_context(context_id) if context_id else resolve_default_negotiation_context()
    return resolved.prompts_dir


def list_prompts(context_id: str | None = None) -> list[dict[str, str]]:
    prompts_dir = _prompts_dir_for_context(context_id)
    prompts: list[dict[str, str]] = []
    for node, file_name in PROMPT_FILES.items():
        path = prompts_dir / file_name
        prompts.append(
            {
                "node": node,
                "file": str(path),
                "base_text": path.read_text(encoding="utf-8") if path.exists() else "",
                "prompt_version": f"{node}_base",
            }
        )
    return prompts
