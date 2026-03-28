# agente-humano
Sistema IA con OpenAI Responses API para agente humano conversacional (chat + negociación).

## Arquitectura actual (sin LangChain/LangGraph)

- Pipeline 3-LLM por turno para `chat` y `negociacion`:
  - Summarizer (trimming + summarizing por turnos)
  - Planner (Structured Outputs con JSON Schema estricto)
  - Executor (respuesta final)
- Entrada de voz por Google STT (`/stt_google`), con credencial por `GOOGLE_SERVICE_ACCOUNT_JSON` o `GOOGLE_CREDENTIALS_PATH` y fallback a OpenAI STT si Google no queda disponible.
- Salida de voz por OpenAI TTS (`/tts`, modelo por defecto `gpt-4o-mini-tts`).
- Endpoints conversacionales:
  - `/chat`
  - `/negociar`


## Configuración

- Dependencias Python: `backend/requirements.txt`.
- Variables de entorno de integración: usa `backend/.env.example` como plantilla.
- **Importante:** la configuración de cada flujo (orden de LLMs, modelos y límites) ahora está definida en:
  - `backend/chat/flow_config.py`
  - `backend/negociacion/orchestration/flow_config.py`



## Dónde está definida la secuencia de LLMs (orden + modelo)

La secuencia y el orden están centralizados en `backend/infra/openai/engine.py`, dentro de `run_three_llm_turn(...)`.
Ese flujo ejecuta siempre este orden por turno:

1. `SummarizerNode`
2. `PlannerNode`
3. `ExecutorNode`

La selección de modelo, el orden de nodos y límites por dominio se define en:
- `backend/chat/flow_config.py` (`CHAT_FLOW_DETAILS`)
- `backend/negociacion/orchestration/flow_config.py` (`NEGOTIATION_FLOW_DETAILS`)

Cada pipeline (`backend/chat/pipeline.py`, `backend/negociacion/pipeline.py`) solo construye la configuración con `build_*_pipeline_config()` y se la pasa al motor común `run_three_llm_turn(...)`.

## Diagnóstico de errores en `api/app.py` y `infra/openai/engine.py`

Si VS Code/Pylance te muestra errores como "No se ha podido resolver la importación ..." o símbolos desconocidos (`speech`, `OpenAI`, etc.), casi siempre es por entorno local y no por APIs mal conectadas.

Causas típicas:
- Intérprete de Python del editor distinto al del terminal/venv.
- Dependencias instaladas en un Python, pero Pylance analizando otro.
- Versión antigua de `openai` que no incluye `openai.OpenAI()`.
- `backend` no añadido a rutas de análisis del editor.

Comprobación rápida:
- `python3 backend/scripts/doctor_imports.py`
- `pyright`

Nota sobre APIs: una API key/credenciales incorrectas causa fallos en runtime (401/403, permisos, credenciales), no errores de importación estática.

## Deploy Railway v1 (scope mínimo)

Objetivo de esta salida: 1 instancia Railway con superficie pública oficial en `/interfaz_usuario` + `/api/interfaz_usuario`.

### Arranque

Con `Procfile` en raíz:

```procfile
web: cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

Si prefieres configurarlo en panel Railway (sin Procfile), usa exactamente:

```bash
cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

### Variables de entorno mínimas en Railway

Obligatoria:
- `OPENAI_API_KEY`

Recomendadas para superficie pública v1:
- `ENABLE_AVATAR_APP=0`
- `ENABLE_OPTIMIZADOR_APP=0`

Opcionales (speech):
- `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`, `OPENAI_TTS_FORMAT`, `OPENAI_TTS_SPEED`, `OPENAI_STT_MODEL`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (Railway recomendado), `GOOGLE_CREDENTIALS_PATH` (local) y `GOOGLE_STT_*`. Prioridad: JSON inline > path > fallback OpenAI STT en `/stt_google`.

### Activación de ramas LLM en `/comunicacion`

La política funcional de activación de ramas LLM está centralizada en código en:
- `backend/evaluacion/engine/communication_activation_policy.py`

Policy efectiva actual (fuente de verdad en código):
- contenido: `llm`
- delivery: `llm`
- visual: `llm_v1`
- síntesis global: `llm`

Variables de entorno relacionadas con este flujo:

```bash
OPENAI_API_KEY=...                       # secreto requerido para llamadas LLM
COMMUNICATION_FORCE_SAFE_MODE=false      # kill switch global opcional (true => fallback/metadata)
COMM_VISUAL_OPENAI_TIMEOUT_S=25          # tuning operativo opcional
COMM_VISUAL_OPENAI_MAX_RETRIES=2         # tuning operativo opcional
```

Los modelos por rama están definidos en código (no en `.env`) en:
- `backend/evaluacion/engine/communication_llm_models.py`

Correspondencia actual:
- `content` -> `gpt-4.1-mini`
- `delivery` -> `gpt-4.1-mini`
- `visual` -> `gpt-4.1-mini`
- `global_synthesis` -> `gpt-4.1-mini`

Notas de observabilidad:
- `disabled_policy`: rama deshabilitada por policy efectiva en código (ej. safe mode).
- `missing_openai_api_key`: policy habilita LLM pero `OPENAI_API_KEY` ausente/vacía.
- visual en `metadata` con `reason=disabled_policy`: esperado en safe mode global.

### Smoke check post-deploy

1. `GET /health` → `{"status":"ok"}`
2. `GET /interfaz_usuario` carga la interfaz pública
3. `POST /api/interfaz_usuario/negociacion/turn` responde `reply`

### Límites explícitos de esta v1

- Estado conversacional en RAM (no reanudación robusta tras reinicio/redeploy).
- Sin multi-réplica en esta fase.
- Esta fase no incluye cambios de sesiones, feedback runtime, persistencia ni integración Moodle.
