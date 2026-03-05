# agente-humano
Sistema IA con OpenAI Responses API para agente humano conversacional (chat + negociación).

## Arquitectura actual (sin LangChain/LangGraph)

- Pipeline 3-LLM por turno para `chat` y `negociacion`:
  - Summarizer (trimming + summarizing por turnos)
  - Planner (Structured Outputs con JSON Schema estricto)
  - Executor (respuesta final)
- Entrada de voz por Google STT (`/stt_google`).
- Salida de voz por OpenAI TTS (`/tts`, modelo por defecto `gpt-4o-mini-tts`).
- Endpoints conversacionales:
  - `/chat`
  - `/negociar`


## Configuración

- Dependencias Python: `backend/requirements.txt`.
- Variables de entorno de integración: usa `backend/.env.example` como plantilla.
- **Importante:** la configuración de modelos del pipeline conversacional (chat/negociación) está definida en código en cada nodo:
  - `backend/chat/pipeline.py`
  - `backend/negociacion/pipeline.py`


## Diagnóstico de errores en `app.py` y `openai_production/engine.py`

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
