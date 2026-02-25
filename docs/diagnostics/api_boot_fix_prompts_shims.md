# API boot fix: prompts shims para `agent.py`

## Símbolos importados desde `prompts` en `backend/agent.py`

Se revisó el bloque `from prompts import (...)` y estos son todos los símbolos requeridos por el entrypoint API:

- `BASE_PERSONALITY_PROMPT`
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT`
- `CONVERSATION_USER_TEMPLATE`

## Shims añadidos en `backend/prompts.py`

Se añadió la sección al final:

`# --- App/Agent entrypoint shims (API) ---`

Con definiciones mínimas (strings simples con `.strip()`) para:

- `BASE_PERSONALITY_PROMPT` (obligatorio)
- `SUMMARY_SYSTEM_PROMPT`
- `SUMMARY_USER_PROMPT`
- `CONVERSATION_USER_TEMPLATE`

Criterios de estilo aplicados en los textos:

- Español
- Sin acciones físicas
- Sin revelar BATNA

## Comandos ejecutados y resultado

1. `python -c "import app; print('app_import_ok')"`
   - Resultado: `app_import_ok`
   - Estado: OK (sin `ImportError`)

2. `python -c "import agent; print('agent_import_ok')"`
   - Resultado: `agent_import_ok`
   - Estado: OK (sin `ImportError`)

3. `uvicorn app:app --host 0.0.0.0 --port 8000`
   - Ejecutado con `timeout 12s` para validación no interactiva.
   - Evidencia de arranque:
     - `Application startup complete.`
     - `Uvicorn running on http://0.0.0.0:8000`
   - Estado: OK (sin `ImportError` durante startup)
