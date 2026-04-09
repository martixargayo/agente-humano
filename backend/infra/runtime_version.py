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


def _first_env(*names: str) -> str | None:
    for name in names:
        value = _safe_env(name)
        if value is not None:
            return value
    return None


@lru_cache(maxsize=1)
def get_runtime_version_info() -> dict[str, str | None]:
    repo_root = Path(__file__).resolve().parents[2]
    git_commit: str | None = _first_env(
        "GIT_COMMIT",
        "COMMIT_SHA",
        "SOURCE_COMMIT",
        "SOURCE_VERSION",
        "RENDER_GIT_COMMIT",
        "RAILWAY_GIT_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
        "HEROKU_SLUG_COMMIT",
        "CI_COMMIT_SHA",
    )
    git_branch: str | None = _first_env(
        "GIT_BRANCH",
        "SOURCE_BRANCH",
        "RENDER_GIT_BRANCH",
        "RAILWAY_GIT_BRANCH",
        "VERCEL_GIT_COMMIT_REF",
        "CI_COMMIT_BRANCH",
    )

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
        "service_version": _first_env("SERVICE_VERSION", "APP_VERSION", "RELEASE_VERSION", "RAILWAY_SERVICE_NAME"),
        "build_id": _first_env("BUILD_ID", "RAILWAY_BUILD_ID", "RENDER_SERVICE_ID", "HEROKU_RELEASE_VERSION"),
        "deploy_env": _first_env("DEPLOY_ENV", "ENVIRONMENT", "RAILWAY_ENVIRONMENT", "VERCEL_ENV", "RENDER_ENV"),
        "git_commit": git_commit,
        "git_branch": git_branch,
    }
