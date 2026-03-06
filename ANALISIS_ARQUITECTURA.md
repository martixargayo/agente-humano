# Análisis de arquitectura del repositorio `agente-humano`

Este documento explica **qué hace cada parte** del repositorio y por qué no existen archivos de Node.js para definir el funcionamiento de las tres LLM.

## 1) Qué es este proyecto

El repositorio implementa un backend en **Python + FastAPI** para un agente conversacional con dos modos (`chat` y `negociación`) y un pipeline de 3 LLM por turno:

1. **Summarizer** (resume contexto antiguo)
2. **Planner** (genera plan estructurado en JSON)
3. **Executor** (redacta la respuesta final)

Además, incluye:
- STT (speech-to-text) con Google, fallback a OpenAI.
- TTS (text-to-speech) con OpenAI.
- Una UI web simple y un avatar 3D en frontend estático.

## 2) Distribución de carpetas y función exacta de cada pieza

### Raíz

- `pyrightconfig.json`: configura análisis estático para que Pyright revise `backend/` y resuelva imports internos.
- `pytest.ini`: configura pytest apuntando a `backend/tests` (aunque en esta versión no hay tests visibles).
- `.vscode/settings.json`: configuración local de editor.

### `backend/`

- `app.py`:
  - Punto de entrada FastAPI.
  - Define endpoints:
    - `/chat` y `/negociar` (conversación)
    - `/stt_google` (transcripción)
    - `/tts` y `/tts_openai` (síntesis de voz)
    - `/demo` (mini UI HTML embebida)
    - `/avatar` (sirve app estática del avatar)
  - Gestiona CORS, carga de `.env`, clientes de Google/OpenAI y warmup de TTS.

- `agent.py`: wrapper de compatibilidad que redirige al pipeline de `chat`.

- `state.py`:
  - Modelo de estado de sesión (`SessionState`) en memoria RAM.
  - Almacén global `SESSIONS`.
  - Funciones para obtener/guardar sesión, añadir mensajes y utilidades de negociación.

- `state_migration_v3.py`:
  - Migraciones simples para normalizar `belief_state` y `world_state` como diccionarios.
  - Evita errores de estructura al arrancar.

- `requirements.txt`: dependencias de Python (FastAPI, OpenAI SDK, Google Speech, etc.).

- `scripts/doctor_imports.py`:
  - Script de diagnóstico para validar imports y versión de OpenAI SDK.
  - Útil para resolver errores de Pylance/Pyright de entorno.

#### `backend/chat/`

- `flow_config.py`:
  - Define los detalles del flujo de chat en `CHAT_FLOW_DETAILS`.
  - Incluye orden de nodos LLM, modelos por nodo y límites de contexto.
- `pipeline.py`:
  - Construye `PipelineConfig` con `build_chat_pipeline_config()`.
  - Llama al motor común `run_three_llm_turn`.
- `prompts/`: plantillas de prompt (actualmente placeholders `prompt pendiente de pegar`).

#### `backend/negociacion/`

- `flow_config.py`:
  - Define los detalles del flujo de negociación en `NEGOTIATION_FLOW_DETAILS`.
  - Incluye orden de nodos LLM, modelos por nodo y límites de contexto.
- `pipeline.py`:
  - Construye `PipelineConfig` con `build_negotiation_pipeline_config()`.
  - Llama al motor común con memoria separada (`negotiation_memory`).
- `prompts/`: plantillas para negociación (también placeholders en esta versión).

#### `backend/openai_production/`

- `engine.py`:
  - Motor real del pipeline de 3 nodos.
  - Componentes:
    - `SessionMemoryManager`: recorte y resumen del historial.
    - `SummarizerNode`: resume prefijo antiguo.
    - `PlannerNode`: genera JSON estricto con schema.
    - `ExecutorNode`: produce respuesta final según plan.
  - Persiste plan y memoria en el estado de sesión.
- `schemas/planner_output.schema.json`: contrato estricto del JSON del planner.

#### `backend/avatar_app/`

Frontend estático (HTML + JS ES modules) para avatar 3D:
- `index.html`: estructura visual y estilos.
- `app.js`: lógica principal de rendering/interacción/avatar/audio/UI.
- `demo_feedback_mode.js`: modo demo con flujo de feedback prefijado.
- `FaceVolumen.glb`: modelo 3D.
- `assets/`: recursos visuales.


## 3.1) Respuesta directa: dónde está el orden y el modelo de cada LLM

- **Orden de ejecución por turno**: está en `backend/openai_production/engine.py`, en `run_three_llm_turn(...)`.
  Allí se instancia y ejecuta en este orden: `SummarizerNode` → `PlannerNode` → `ExecutorNode`.
- **Modelo de cada LLM y orden por flujo**: se fija en los archivos de dominio:
  - `backend/chat/flow_config.py`: `CHAT_FLOW_DETAILS` + `build_chat_pipeline_config()`.
  - `backend/negociacion/flow_config.py`: `NEGOTIATION_FLOW_DETAILS` + `build_negotiation_pipeline_config()`.
- Esos valores se pasan mediante `PipelineConfig` al motor común.

## 3) Por qué no hay archivos Node.js para “definir las 3 LLM”

No hay archivos de Node por diseño arquitectónico:

1. **El backend está implementado en Python**, no en Node.
   - La lógica de las 3 LLM vive en `backend/openai_production/engine.py`.
   - La configuración por dominio (chat/negociación) vive en `backend/chat/flow_config.py` y `backend/negociacion/flow_config.py`.

2. **No existe cadena de build Node para el frontend**.
   - El avatar usa módulos ES nativos en navegador y un `importmap` que carga `three` desde CDN.
   - Por eso no se necesitan `package.json`, `node_modules`, ni scripts npm para funcionar.

3. **Separación clara de responsabilidades**.
   - Python/FastAPI: orquestación IA + estado + APIs + STT/TTS.
   - HTML/JS estático: visualización y experiencia de avatar.
   - Resultado: sistema más simple para MVP, con menos tooling y menos pasos de despliegue.

## 4) Funcionamiento de extremo a extremo

1. Cliente llama `/chat` o `/negociar`.
2. `app.py` recupera sesión (`state.py`) y delega en pipeline correspondiente.
3. Pipeline invoca motor 3-LLM (`openai_production/engine.py`):
   - Trim/resumen si el contexto creció.
   - Planner produce JSON validado por schema.
   - Executor redacta respuesta.
4. Se guarda estado actualizado y se devuelve reply.
5. Opcionalmente, UI llama STT/TTS para voz.

## 5) Conclusión

La ausencia de “archivos Node para las 3 LLM” **no es un hueco**, sino una decisión de arquitectura:
- LLM/orquestación en Python (backend).
- Frontend estático sin build Node.
- Estructura modular por dominio (`chat`, `negociación`) y un motor común reutilizable.
