# Guía práctica: eliminar negociación y dejar solo `/chat`

Esta guía te permite quitar completamente el sistema de negociación del backend y mantener únicamente el flujo de chat general.

## Objetivo final

Después de aplicar estos pasos:

- El backend seguirá levantando con `/health`, `/chat`, `/tts`, etc.
- El endpoint `/negociar` ya no existirá.
- No se cargarán dependencias de `negotiation.*` en `app.py`.
- El código de negociación quedará aislado para poder borrarlo en una segunda fase sin romper el arranque.

---

## Paso 1) Desconectar negociación del `app.py`

Archivo: `backend/app.py`.

### 1.1 Elimina imports de negociación

Quita estos imports:

- `from negotiation.negotiation_graph import run_negotiation_agent`
- `from negotiation.summary_jobs import SUMMARY_JOBS, deferred_summary_enabled, make_turn_job`
- `from negotiation.state.deps import DEFAULT_DEPS`
- `from negotiation.telemetry.live_trace import ...`
- `from negotiation.telemetry.live_trace2 import ...`

### 1.2 Elimina hooks de startup/shutdown de summary worker

Borra:

- `startup_summary_worker()`
- `shutdown_summary_worker()`

### 1.3 Elimina endpoint `/negociar`

Borra completo:

- `@app.post("/negociar", response_model=ChatResponse)`
- función `negociar_endpoint(...)`

### 1.4 Elimina endpoints de trazas de negociación

Borra todo lo relacionado a:

- `_trace_sse_generator`
- `/negociacion/trazas/stream`
- `_livetrace2_sse_generator`
- `_livetrace2_stream_response`
- `/negociacion/livetrace2/stream`
- HTML de `livetrace2_view` si lo tienes embebido en ese archivo.

Con esto dejas el backend sin rutas runtime de negociación.

---

## Paso 2) Verificar que `/chat` siga funcionando

Mantén tal cual:

- `ChatRequest` / `ChatResponse`
- endpoint `@app.post("/chat")`
- llamada `run_agent(state, payload.message)`

Ese camino ya es independiente de negociación y seguirá funcionando si no rompes sus imports (`state`, `agent`).

---

## Paso 3) Quitar dependencias de negociación del runtime

Revisa si `backend/requirements.txt` incluye librerías que solo usabas para negociación. Si existen y no se usan en chat, elimínalas en una segunda pasada (primero confirma que arranca y responde `/chat`).

Sugerencia: haz esto en dos commits separados:

1. **Desconexión funcional** (rutas/imports).
2. **Limpieza de dependencias**.

---

## Paso 4) Limpieza de código muerto (fase 2)

Una vez validado que `/chat` funciona, puedes borrar el árbol de negociación:

- `backend/negotiation/**`
- `docs/*` que describan negociación y ya no quieras mantener
- `reports/*` de diagnóstico de negociación (opcional)

Importante: antes de borrar en masa, corre búsqueda de referencias para evitar imports colgantes:

```bash
rg "\bnegotiation\b|/negociar|livetrace2|trazas/stream" backend docs scripts
```

---

## Paso 5) Checklist de validación mínima

Ejecuta al menos:

```bash
python -m py_compile backend/app.py backend/agent.py backend/state.py
pytest -q
```

Y prueba manual HTTP:

```bash
# salud
curl -s http://localhost:8000/health

# chat
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","session_id":"s1","message":"hola"}'

# negociar (debe 404)
curl -i -X POST http://localhost:8000/negociar \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","session_id":"s1","message":"hola"}'
```

Resultado esperado:

- `/health` responde 200.
- `/chat` responde 200 con `reply`.
- `/negociar` responde 404.

---

## Implementación rápida (resumen ejecutivo)

Si quieres hacerlo rápido y seguro:

1. Edita `backend/app.py` y borra todo lo de negociación (imports + rutas + workers + trace SSE).
2. Arranca backend y confirma que `/chat` funciona.
3. En un segundo commit, borra `backend/negotiation` y documentación asociada.

Si quieres, en un siguiente paso te puedo preparar directamente el **patch exacto en `backend/app.py`** para dejarlo ya aplicado y listo para commit.
