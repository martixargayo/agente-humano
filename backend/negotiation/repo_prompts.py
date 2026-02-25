from __future__ import annotations

import importlib.util
from pathlib import Path

_PROMPTS_PATH = Path(__file__).resolve().parents[1] / "prompts.py"
_SPEC = importlib.util.spec_from_file_location("_repo_prompts", _PROMPTS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"No se pudo cargar prompts del repo: {_PROMPTS_PATH}")

_repo_prompts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_repo_prompts)

SUMMARY_SYSTEM_PROMPT = _repo_prompts.SUMMARY_SYSTEM_PROMPT
SUMMARY_USER_PROMPT = _repo_prompts.SUMMARY_USER_PROMPT
WORLD_JUDGE_V3_SYSTEM_PROMPT = _repo_prompts.WORLD_JUDGE_V3_SYSTEM_PROMPT
WORLD_JUDGE_V3_USER_PROMPT = _repo_prompts.WORLD_JUDGE_V3_USER_PROMPT
PLANNER_SEMANTIC_V1_SYSTEM_PROMPT = _repo_prompts.PLANNER_SEMANTIC_V1_SYSTEM_PROMPT
PLANNER_SEMANTIC_V1_USER_PROMPT = _repo_prompts.PLANNER_SEMANTIC_V1_USER_PROMPT
