# Auditoría técnica del repositorio para despliegue en Railway + integración Moodle

> **Alcance de esta fase**: análisis técnico del estado actual, sin modificar código de runtime.
> 
> **Convención**:
> - **[HECHO]**: observado directamente en código.
> - **[INFERENCIA]**: deducción razonable a partir del código, pendiente de validación empírica.

## A. Resumen ejecutivo

- **[HECHO]** El repositorio implementa un backend FastAPI con endpoints conversacionales (`/chat`, `/negociar`), endpoints de voz (`/stt_google`, `/tts`, `/tts_openai`) y superficies UI estáticas servidas por el mismo proceso (`/avatar`, `/interfaz_usuario`, `/optimizador`).
- **[HECHO]** La arquitectura de diálogo usa OpenAI Responses API con pipelines multi-nodo:
  - chat simple: `summarizer -> planner -> executor`.
  - negociación avanzada: `memory + phase_classifier (paralelo) -> planner -> executor` + guardrails + trazas.
- **[HECHO]** El estado de sesión y gran parte de la persistencia son **en memoria del proceso** (`SESSIONS` global y repositorio de feedback en memoria), sin base de datos externa.
- **[HECHO]** Existen acoplamientos de entorno local (carga explícita de `backend/.env`, path por defecto de credenciales Google STT apuntando a ruta local de desarrollo, ausencia de configuración de `PORT/HOST`).
- **[HECHO]** El sistema puede responder en modo degradado sin `OPENAI_API_KEY` (fallbacks), pero con pérdida significativa de comportamiento “inteligente”.
- **[INFERENCIA]** Como backend para Moodle multiusuario y despliegue cloud escalable, **no está listo tal cual**: falta persistencia durable de sesiones/conversaciones/jobs, aislamiento robusto por usuario/actividad, y adaptación explícita a despliegue PaaS (Railway).

## B. Mapa del sistema

### 1) Backend HTTP/API

- **Entry point principal**: `backend/api/app.py` (`app = FastAPI(...)`).
- Endpoints principales:
  - `/health`
  - `/chat` (pipeline chat legacy/simple)
  - `/negociar` (pipeline negociación)
  - `/stt_google` (Google STT con fallback a OpenAI transcribe)
  - `/tts` (TTS OpenAI y respuesta base64)
  - `/tts_openai` (TTS OpenAI streaming)
  - Router moderno de IU en `/api/interfaz_usuario/...` (turnos, sesiones, feedback).

### 2) Frontend / interfaz

- **[HECHO]** Se sirven apps estáticas desde el propio FastAPI:
  - `/avatar` -> `backend/avatar_app`
  - `/interfaz_usuario` -> `backend/interfaz_usuario_app`
  - `/optimizador` -> `backend/avatar_app/optimizador`
- **[HECHO]** `interfaz_usuario_app` usa la API moderna `/api/interfaz_usuario`.
- **[HECHO]** `avatar_app` aún llama directamente a `/chat` o `/negociar` y además usa `user_id/session_id` hardcodeados en un flujo (`web_user`, `sesion_demo`), lo que es crítico para multiusuario.

### 3) Núcleo conversacional / orquestación LLM

- **Chat**: `backend/chat/pipeline.py` delega en `run_three_llm_turn(...)` de `backend/infra/openai/engine.py`.
- **Negociación**: `backend/negociacion/pipeline.py` usa `run_negotiation_cognitive_turn(...)` en `backend/negociacion/orchestration/flow_config.py`.
- **Negociación cognitiva**:
  - Estado canónico tipado (`CanonicalState`), contexto OpenAI thread/conversation, memoria episódica.
  - Nodos memory y phase classifier en paralelo (`ThreadPoolExecutor(max_workers=2)`), luego planner y executor secuenciales.
  - Guardrails de entrada/salida + trazas detalladas por turno.

### 4) Audio / tiempo real

- **Entrada audio**: `/stt_google` recibe upload y usa Google Cloud Speech; fallback OpenAI transcriptions.
- **Salida audio**: `/tts` y `/tts_openai` con OpenAI TTS.
- **[HECHO]** Existe prefetch/caché en memoria para TTS.
- **[HECHO]** No se observan WebSockets/SSE; la interacción parece request/response HTTP + polling en feedback.

### 5) Feedback/evaluación

- Router en `/api/interfaz_usuario/feedback/...`.
- Jobs lanzados en `ThreadPoolExecutor(max_workers=4)` dentro del mismo proceso web.
- Repositorio de jobs/reportes en memoria (`InMemoryFeedbackRepository`).

## C. Flujo completo de ejecución (end-to-end)

### Flujo 1: IU moderna (`/interfaz_usuario`) -> negociación

1. Cliente JS (`interfaz_usuario_app/app.js`) llama a `/api/interfaz_usuario/negociacion/turn`.
2. `interfaz_usuario` router delega a `services.run_turn(...)`.
3. `run_turn` obtiene/crea `SessionState` vía `get_session_state(user_id, session_id)` (diccionario global en RAM).
4. Se construye `NegotiationTurnConfig` desde `build_negotiation_pipeline_config()`.
5. `execute_turn_with_contract(...)` ejecuta el pipeline cognitivo con metadatos de entry contract.
6. En `run_negotiation_cognitive_turn(...)`:
   - Carga estado canónico desde `state.world_state[memory_key]`.
   - Corre guardrails de entrada.
   - Si permitido: ejecuta memory + phase classifier en paralelo (ambos Structured Outputs JSON).
   - Aplica outputs al estado canónico, evalúa reglas de botón finalizar.
   - Ejecuta planner (JSON estructurado) y executor (JSON estructurado con `spoken_text`).
   - Aplica guardrails de salida, guarda traza completa del turno.
   - Persiste en `state.world_state` y `state.history` (RAM).
7. Respuesta vuelve al frontend con `reply`, ids de conversación/thread y `finish_button_armed`.
8. Si el frontend está en modo voz, puede llamar a `/tts` para sintetizar la respuesta.

### Flujo 2: IU avatar legacy (`/avatar`) -> `/chat` o `/negociar`

1. JS en `avatar_app/app.js` elige endpoint por modo (`/chat` o `/negociar`).
2. Envía payload con `user_id/session_id` (en el snippet auditado aparecen hardcodeados para demo).
3. `/chat` ejecuta `run_agent -> run_chat_agent -> run_three_llm_turn`.
4. `/negociar` ejecuta `run_negotiation_agent -> run_negotiation_cognitive_turn`.
5. Devuelve `reply` y opcionalmente `finish_button_armed`.

### Flujo de voz

1. Frontend graba audio y lo sube a `/stt_google`.
2. Backend intenta Google STT; si falla y hay OpenAI client, usa OpenAI transcriptions.
3. Texto resultante entra al flujo conversacional.
4. Reply textual puede pasarse a `/tts` para devolver audio base64 o a `/tts_openai` para streaming bytes.

## D. Riesgos para despliegue en Railway (por criticidad)

### Bloqueantes

1. **Persistencia de sesión en RAM** (diccionario global `SESSIONS`): pérdida total al reinicio/deploy, sin compartir estado entre réplicas.
2. **Persistencia de feedback en RAM** (`InMemoryFeedbackRepository`): jobs/reportes se pierden al reiniciar; no escalable entre instancias.
3. **Dependencias de filesystem local para credenciales Google** (`GOOGLE_CREDENTIALS_PATH` con fallback local de dev).
4. **Ausencia de configuración explícita de arranque cloud (PORT/HOST)** dentro del repo (sin Dockerfile/Procfile/railway config ni script de arranque documentado).

### Importantes

1. **Jobs de evaluación embebidos en el web process** (`ThreadPoolExecutor` local): compiten con peticiones HTTP y no sobreviven a reinicios.
2. **Cachés globales en memoria para TTS** (`_tts_audio_cache`, `_tts_inflight_tasks`): sin límites explícitos ni compartición entre instancias.
3. **CORS abierto a `*`**: aceptable en dev, arriesgado en producción Moodle.
4. **Uso de múltiples superficies API (legacy y moderna)** con contratos diferentes: aumenta riesgo operacional.

### Deseables

1. Endurecer observabilidad (métricas/structured logging/trace ids cross-request).
2. Definir estrategia de secretos en Railway (OpenAI, Google).
3. Aislar mejor assets pesados 3D/audio y su serving/caching.

## E. Riesgos multiusuario y concurrencia

1. **Estado global compartido por proceso** (`SESSIONS`):
   - riesgo alto en despliegues con múltiples réplicas (sticky session o inconsistencia).
   - sesiones no accesibles entre instancias.
2. **Mezcla de usuarios por IDs no robustos**:
   - [HECHO] En `avatar_app` hay uso hardcodeado de `user_id/session_id` demo, lo que puede mezclar conversaciones si se usa tal cual en producción.
3. **Sin storage transaccional para turnos/sesiones**: dos requests simultáneos sobre la misma sesión pueden sobrescribir evolución de estado (last write wins implícito).
4. **Locks parciales**:
   - feedback repo tiene `Lock` interno (solo jobs/reportes).
   - `SummarizingSession` usa `asyncio.Lock` en una abstracción puntual.
   - **No hay** lock global por `(user_id, session_id)` para todo el pipeline.
5. **Dependencia de single-process semantics**:
   - comportamiento actual está optimizado para una instancia con memoria caliente.

## F. Requisitos de infraestructura probables en cloud

- **Web service**: FastAPI (1 servicio HTTP).
- **Base de datos** (recomendado bloqueante para producción): para sesiones, turnos, trazas, metadata de conversación, mapping Moodle user/attempt/activity.
- **Redis (recomendado)**: colas, locks distribuidos por sesión, caché de TTS/transient state.
- **Worker service**: para evaluaciones feedback asíncronas (separar del web process).
- **Object storage** (según alcance): opcional para audios/transcripciones/trazas voluminosas.
- **Secret manager/env vars**: OpenAI key, Google creds (idealmente JSON inline/base64 + montaje seguro), toggles de features.
- **Dominio público + TLS**: requerido para integración Moodle/LTI y permisos de micrófono en navegador.

## G. Diseño recomendado para evolucionarlo (sin aplicar cambios aún)

1. **Separar capas explícitamente**:
   - `presentation` (avatar/interfaz/moodle adapters)
   - `conversation service` (turn orchestration)
   - `state/session service` (repositorios + locking)
   - `llm provider adapter` (OpenAI encapsulado)
   - `scenario config` (negociación, conversación difícil, etc.)
2. **Modelo de identidad/sesión para Moodle**:
   - `platform_user_id` (Moodle user)
   - `activity_id` / `scenario_id`
   - `attempt_id` (intento evaluable)
   - `conversation_id` técnico (interno)
   - clave compuesta recomendada: `(tenant/course, activity_id, attempt_id, user_id)`.
3. **Persistir eventos de turno** (event sourcing ligero): input, outputs de nodos, guardrails, latencias, reply final.
4. **Control de concurrencia por sesión**:
   - lock distribuido por `attempt_id` o `conversation_id`.
   - idempotency key por turno para evitar duplicados.
5. **Escenarios múltiples**:
   - mover prompts/modelos/reglas a configuración versionada por `scenario_id`.
   - mantener pipeline base común y enchufar “domain modules”.

## H. Capacidad para múltiples actividades Moodle (estado actual)

- **[HECHO]** Ya existe cierta modularidad por dominio (`chat`, `negociacion`, `evaluacion/domains/negotiation`) y prompts en carpetas.
- **[HECHO]** Pero hay piezas hardcodeadas al caso negociación (fases, phase cards, reglas botón finalizar, rubric negociación).
- **[INFERENCIA]** Es viable evolucionar a `scenario_id/activity_type` sin rehacer todo, **si** se extraen y parametrizan:
  - contratos de estado canónico por escenario,
  - prompts y schemas por escenario,
  - guardrails/rúbricas por escenario,
  - políticas de finalización por escenario.

## I. Lista de archivos y carpetas clave

- `backend/api/app.py`: composición de FastAPI, routers, static mounts, STT/TTS, endpoints legacy.
- `backend/sessions/state.py`: definición de `SessionState`, almacén global `SESSIONS`, ciclo de vida de sesión.
- `backend/infra/openai/engine.py`: pipeline 3-LLM de chat, memoria resumida, planner/executor.
- `backend/negociacion/orchestration/flow_config.py`: pipeline cognitivo principal de negociación, guardrails, tracing, contexto OpenAI thread.
- `backend/interfaz_usuario/services.py` y `backend/interfaz_usuario/__init__.py`: API moderna recomendada para IU.
- `backend/interfaz_usuario_app/app.js`: frontend principal actual (voz + turnos + feedback).
- `backend/avatar_app/app.js`: superficie legacy con rutas `/chat|/negociar` y defaults demo.
- `backend/evaluacion/engine/service.py`: jobs asíncronos de evaluación dentro del proceso.
- `backend/evaluacion/storage/in_memory_repository.py`: persistencia en memoria de feedback.
- `backend/requirements.txt`: stack Python y librerías núcleo.

## J. Dudas abiertas (requieren validación posterior)

1. ¿Cuál será el mecanismo exacto de integración con Moodle (LTI, plugin propio, JWT backend-to-backend)?
2. ¿Se exige reanudación exacta de sesión entre días/dispositivos y auditoría completa por intento?
3. ¿Qué SLA de concurrencia/latencia se espera (usuarios simultáneos por curso)?
4. ¿Debe persistirse audio crudo/transcripciones por compliance o basta texto?
5. ¿Se desplegará una sola instancia Railway o varias réplicas autoscaling?
6. ¿Qué política de retención y borrado de datos de estudiantes aplica?

## Diagrama textual: arquitectura actual

```text
[Navegador /interfaz_usuario o /avatar]
        |
        v
[FastAPI backend/api/app.py]
  |- static mounts (/avatar, /interfaz_usuario, /optimizador)
  |- /chat -> chat pipeline (infra/openai/engine.py)
  |- /negociar -> negociación pipeline (negociacion/orchestration/flow_config.py)
  |- /stt_google -> Google STT -> fallback OpenAI STT
  |- /tts,/tts_openai -> OpenAI TTS (+ cache RAM)
  |- /api/interfaz_usuario/* -> services + feedback
        |
        +--> [SESSIONS dict en RAM: estado conversación]
        +--> [InMemoryFeedbackRepository: jobs/reportes RAM]
        +--> [OpenAI Responses API]
        +--> [Google Speech API]
```

## Diagrama textual: arquitectura objetivo para Railway (propuesta)

```text
[Moodle Activity] --(auth context: user/activity/attempt)--> [Backend API]
                                  |
                                  v
                        [Session Service Layer]
                      (locks por attempt/conversation)
                                  |
               +------------------+------------------+
               |                                     |
               v                                     v
       [Conversation Orchestrator]         [Feedback Job Producer]
               |                                     |
               v                                     v
       [LLM Adapter (OpenAI)]                [Queue/Worker]
               |                                     |
               v                                     v
      [Postgres: sesiones/turnos/trazas]   [Postgres + object storage opcional]
               |
               v
        [Redis: cache + distributed locks + ephemeral state]
```
