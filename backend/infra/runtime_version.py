from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path


def _safe_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@lru_cache(maxsize=1)
def get_runtime_version_info() -> dict[str, str | None]:
    repo_root = Path(__file__).resolve().parents[2]
    git_commit: str | None = _safe_env("GIT_COMMIT") or _safe_env("COMMIT_SHA")
    git_branch: str | None = _safe_env("GIT_BRANCH")

    if git_commit is None:
        try:
            git_commit = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                .strip()
                or None
            )
        except Exception:
            git_commit = None

    if git_branch is None:
        try:
            git_branch = (
                subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=repo_root,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                .strip()
                or None
            )
        except Exception:
            git_branch = None

    return {
        "service_version": _safe_env("SERVICE_VERSION") or _safe_env("APP_VERSION"),
        "build_id": _safe_env("BUILD_ID"),
        "deploy_env": _safe_env("DEPLOY_ENV"),
        "git_commit": git_commit,
        "git_branch": git_branch,
    }
