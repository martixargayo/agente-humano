# AGENTS.md

## Project

This repository contains a Python/FastAPI application deployed to Railway from the `main` branch. The public Moodle integration depends on the Railway URL, so production safety matters.

## Local Setup

- Use the repository root as the working directory.
- Python dependencies live in `backend/requirements.txt`.
- The app loads local environment variables from `backend/.env`.
- The Railway start command is:
  `cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}`
- The local equivalent is:
  `.\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir backend --host 127.0.0.1 --port 8000`

## Git Workflow

- Do not work directly on `main` for code changes.
- Create a branch with the `codex/` prefix for Codex work.
- Keep commits focused and test before pushing.
- Push the branch to GitHub and merge to `main` only after review.
- Railway deploys production from `main`, so merging to `main` is the production release step.

## Verification

- Run targeted tests for changed areas whenever possible.
- Install test tooling locally with:
  `.\.venv\Scripts\python.exe -m pip install pytest`
- For a broad check, run:
  `.\.venv\Scripts\python.exe -m pytest`
- For a quick server check, run the app locally and open:
  `http://127.0.0.1:8000/health`

## Secrets

- Never commit `backend/.env`, API keys, Google service account JSON files, or Railway secrets.
- Local missing secrets to fill manually:
  - `OPENAI_API_KEY`
  - `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_CREDENTIALS_PATH`, only if Google STT is needed locally.
