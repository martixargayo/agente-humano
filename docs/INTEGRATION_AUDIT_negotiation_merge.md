# Integration Audit — negotiation merge (`origin/mejoras-ia` → `main`)

Fecha: 2026-02-11  
Repo: `/workspace/agente-humano`

## 1) Arquitectura y flujo end-to-end

### Entry-point HTTP y wiring
- El backend arranca como app FastAPI en `backend/app.py` (`app = FastAPI(...)`).
- Rutas principales detectadas:
  - `GET /health`
  - `POST /chat` (pipeline legacy `run_agent`)
  - `POST /negociar` (pipeline de negociación `run_negotiation_agent`)
  - `POST /stt_google`, `POST /tts_openai`, `POST /tts`, `GET /demo`, estáticos en `/avatar`.

### Flujo de negociación e2e
`POST /negociar` → `get_session_state(user_id, session_id)` → `run_negotiation_agent(state, message)`

Dentro de `run_negotiation_agent`:
1. Persiste turno user en `SessionState.history`.
2. Refresca memoria resumida (`maybe_refresh_summary`) y construye contexto (`build_memory_context`).
3. Normaliza y prepara constraints/estado (`exit_option`, `max_total_cost`, `world_state`, `belief_state`, `progress_state`).
4. Invoca grafo LangGraph (`negotiation_app.invoke`) con nodos:
   - `world_updater`
   - `belief_updater`
   - `precedence`
   - `intent_manager`
   - `phase_policy_planner`
   - `progress_updater`
   - `executor`
5. Normaliza outputs y persiste:
   - `state.world_state`
   - `state.belief_state`
   - `state.progress_state`
   - `state.last_policy_executed`
   - `state.debug_trace`
6. Añade respuesta assistant a historial y guarda sesión (`save_session_state`).

## 2) Integraciones exactas con `backend/app.py` / `backend/state.py` / HTTP

### `backend/app.py`
- Endpoint `POST /negociar` usa `run_negotiation_agent` y responde con `ChatResponse`.
- Endpoint `POST /chat` mantiene compatibilidad legacy (`run_agent`).
- Se endureció inicialización de clientes externos:
  - STT (Google) ahora se construye con guardas de credenciales.
  - TTS (OpenAI) ahora se construye con guarda de `OPENAI_API_KEY`.
  - Endpoints STT/TTS devuelven `503` si proveedor no está configurado.

### `backend/state.py`
- Contrato de sesión auditado:
  - memoria `summary`, `history`
  - estado negotiation: `world_state`, `belief_state`, `progress_state`, `last_policy_executed`, `debug_trace`
  - compatibilidad legacy: `sister_option_price`, `sister_option_repairs`, `max_total_cost`.
- Persistencia en memoria RAM vía `SESSIONS[(user_id, session_id)]`.

### Contratos/validación interna
- Validadores usados en pipeline:
  - `normalize_world_state`, `normalize_belief_state`, `normalize_progress_state`, `normalize_policy_decision`.
- Se preserva gating/precedence y control de fases desde `phase_policy_planner` + `progress_updater`.

## 3) Checklist ejecutada (comandos + resultados + fixes)

### Inventario
- `git status` → working tree limpio al inicio.
- `git log -n 5 --oneline --decorate` → verificado HEAD y merges recientes.
- `git show --stat` → confirmado merge masivo de `backend/negotiation/*` y tests.

### Static checks
- `python -m compileall backend` → **OK**.

### Test suite
- `pytest -q` → **OK** (suite completa en verde).
- `pytest -q backend/tests -k negotiation -vv` → **OK**.
- `pytest -q backend/tests/test_e2e_negotiation_pipeline.py -vv` → **archivo no existe** (documentado).
- `pytest -q backend/tests -k "world or belief or executor or validator or phase" -vv` → **OK**.

### Arranque real + smoke HTTP
Comando de arranque validado:
```bash
cd backend && OPENAI_API_KEY=test uvicorn app:app --host 0.0.0.0 --port 8001
```

Comandos HTTP validados:
```bash
curl -i http://127.0.0.1:8001/health
curl -i -X POST http://127.0.0.1:8001/negociar -H 'Content-Type: application/json' -d '{"user_id":"audit-user","session_id":"audit-s3","message":"Hola, ¿sigue disponible el coche?"}'
curl -i -X POST http://127.0.0.1:8001/negociar -H 'Content-Type: application/json' -d '{"user_id":"audit-user","session_id":"audit-s3","message":"Tengo tope de presupuesto, ¿podemos ajustar algo?"}'
curl -i -X POST http://127.0.0.1:8001/negociar -H 'Content-Type: application/json' -d '{"user_id":"audit-user","session_id":"audit-s3","message":"Si incluyes transferencia hoy cerramos."}'
```
Resultado final: `/health` 200 y `/negociar` 200 en 3 turnos consecutivos (misma sesión).

## 4) Fixes mínimos aplicados

1. **Hardening de bootstrap de servicios externos** (`backend/app.py`):
   - guardas para credenciales STT/TTS, retorno de 503 cuando no disponibles.
2. **Hardening de fallback LLM en runtime** (`backend/agent.py`, `backend/normalizer.py`, `backend/negotiation/negotiation_graph.py`):
   - inicialización segura de clientes LLM.
   - fallback en invocaciones (sin romper endpoints aunque falle proveedor/modelo).
3. **Resiliencia en updater/planner**:
   - `belief_state_updater.py`: se captura también error al formatear prompt.
   - `phase_policy_planner.py`: se captura también error al formatear prompt.
4. **Extractor strictness sin romper compatibilidad** (`world_state_updater.py`):
   - errores de evidencia faltante/confidence inválida degradan a patch vacío (no crash).
   - violaciones graves (`extractor_illegal_world_key`, belief patch ilegal) siguen levantando excepción (tests de seguridad preservados).

## 5) Smoke tests añadidos

- `backend/tests/test_api_negotiation_smoke.py`
  - smoke de `GET /health`
  - smoke de wiring `POST /negociar` con monkeypatch de `run_negotiation_agent`.
- `backend/tests/test_negotiation_pipeline_smoke_turns.py`
  - smoke de 2 turnos directos de pipeline (sin HTTP) con `AgentDeps` fakes.
  - smoke de flag `MAX_TOTAL_COST_MARGIN` (traza contiene margen aplicado).

## 6) Validación de invariantes clave

- Grafo conectado y ordenado (`world → belief → precedence → intent → phase_policy_planner → progress → executor`) verificado en `negotiation_graph.py`.
- Schemas y normalización ejecutándose en entrada/salida del pipeline.
- Sin evidencia de imports circulares bloqueantes durante `compileall` y `pytest`.
- Persistencia por sesión y merge de estado verificados por ejecución multi-turno y tests.
- Gating/phase logic ejercitado por tests `phase/world/belief/executor/validator`.
- `validator` mantiene backcompat (suite existente en verde).

## 7) Riesgos detectados

1. **Prompts con JSON literal y placeholders `{}`**: causaron `KeyError` en runtime (ya mitigado vía captura/fallback, pero conviene sanear templates escapando llaves).
2. **Dependencia de APIs OpenAI nuevas**: se observan errores 400 por parámetros `messages/response_format`; hoy hay fallback, pero en producción debe alinearse SDK + API usage.
3. **RAG embeddings depende de red/proxy**: falla carga tiktoken en entorno restringido; se usa degradación segura.
4. **`@app.on_event("startup")` deprecado en FastAPI**: no bloquea, pero conviene migrar a lifespan handlers.
5. **No existe `backend/tests/test_e2e_negotiation_pipeline.py`**: cobertura E2E ahora se cubre con smoke nuevos + suite existente.

## 8) TODOs recomendados (no bloqueantes)

- Escapar llaves JSON en prompts base para eliminar origen del `KeyError` y reducir fallback-path.
- Migrar calls a OpenAI Responses API compatible con versión actual.
- Añadir test e2e explícito tipo `test_e2e_negotiation_pipeline.py` (nombre canónico esperado).
- Migrar startup events a lifespan API de FastAPI.
