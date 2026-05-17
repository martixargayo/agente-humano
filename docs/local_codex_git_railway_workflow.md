# Local Codex, GitHub, and Railway Workflow

## Current Setup

- Local path: `C:\Users\Usuario\Documents\New project\agente-humano`
- GitHub remote: `https://github.com/martixargayo/agente-humano.git`
- Production branch: `main`
- Railway deploy command:
  `cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}`
- Local app command:
  `.\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir backend --host 127.0.0.1 --port 8000`

## Daily Flow

1. Update local `main`.

   ```powershell
   git switch main
   git pull
   ```

2. Create a safe work branch.

   ```powershell
   git switch -c codex/nombre-del-cambio
   ```

3. Start Codex from the repo root.

   ```powershell
   codex
   ```

4. Test locally.

   ```powershell
   .\.venv\Scripts\python.exe -m pip install pytest
   .\.venv\Scripts\python.exe -m pytest
   .\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir backend --host 127.0.0.1 --port 8000
   ```

5. Push the branch.

   ```powershell
   git push -u origin codex/nombre-del-cambio
   ```

6. Open a pull request into `main`.

7. Merge to `main` only when ready. Railway will deploy production after that merge.

## Local Secrets To Add

Edit `backend/.env` locally and add:

```dotenv
OPENAI_API_KEY=...
```

Optional for Google STT local testing:

```dotenv
GOOGLE_CREDENTIALS_PATH=C:\ruta\a\google-service-account.json
```

Railway keeps its own environment variables in Railway. Local `backend/.env` is only for this computer.

## Notes

- `backend/.env` is ignored by Git.
- `.venv/` is ignored by Git.
- `ffmpeg` is installed in Railway through `nixpacks.toml`, but it is not currently available in this Windows PATH. Install it locally only if you need to test video/audio processing paths that call `ffmpeg`.
