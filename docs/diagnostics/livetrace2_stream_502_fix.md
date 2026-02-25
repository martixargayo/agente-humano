# LiveTrace2 stream 502 fix (diagnóstico + corrección mínima)

## Repro obligatoria

### Antes del fix

Comandos ejecutados:

1. `curl -i http://127.0.0.1:8000/livetrace2/stream`
   - Resultado: `HTTP/1.1 404 Not Found`

2. `curl -N http://127.0.0.1:8000/livetrace2/stream | head -n 30`
   - Resultado: `{"detail":"Not Found"}`

3. `curl -i http://127.0.0.1:8000/negociacion/livetrace2/stream`
   - Resultado inicial: `HTTP/1.1 200 OK` + conexión cortada (`curl: (18) transfer closed with outstanding read data remaining`).

Traceback capturado en consola Uvicorn:

```text
TypeError: list_recent_livetrace2_events() missing 1 required positional argument: 'trace_items'
...
File "/workspace/agente-humano/backend/app.py", line 355, in _livetrace2_sse_generator
    for event in list_recent_livetrace2_events()
```

## Endpoint real y registro de ruta

Búsqueda:

- `rg -n "livetrace2|/stream|StreamingResponse|text/event-stream|EventSource" backend -S`

Rutas encontradas:

- `/negociacion/livetrace2/stream` en `backend/app.py`
- `/negociacion/livetrace2` en `backend/app.py`
- EventSource en panel: `new EventSource('/negociacion/livetrace2/stream')`

Además se añadió alias explícito para compatibilidad:

- `/livetrace2/stream`
- `/livetrace2`

## Causa raíz del 502

Caso **A**: el backend lanzaba excepción dentro del generator SSE.

- `_livetrace2_sse_generator` llamaba `list_recent_livetrace2_events()` sin argumentos.
- La definición real previa exigía `trace_items` obligatorio.
- El stream explotaba durante la iteración y el proxy/browser podía mostrar 502.

## Fix mínimo aplicado (SSE hardening)

Se aplicó hardening en `LiveTrace2` sin reintroducir runtime legacy:

1. Mantener `StreamingResponse(..., media_type="text/event-stream")`.
2. Primer `yield` inmediato: `": connected\n\n"`.
3. Keepalive SSE cada ~12s: `": ping\n\n"`.
4. Headers SSE:
   - `Cache-Control: no-cache`
   - `Connection: keep-alive`
   - `X-Accel-Buffering: no`
5. `try/except` en el generator para evitar crash silencioso y loggear error.
6. Alias de ruta para que `/livetrace2/stream` funcione también.

## Store/buffer de eventos y verificación de escritura

- `record_gate_event` y `record_llm_call` escriben en `state["trace_runtime"]`.
- `run_negotiation_agent` persiste trazas por turno en `state.debug_trace`.
- LiveTrace2 lee `session.debug_trace` y ahora además mantiene buffer in-memory ring (`deque`) en `negotiation/telemetry/live_trace2.py` con:
  - `append_livetrace2_event(event)`
  - `list_recent_livetrace2_events(limit=...)`

Con esto, el stream puede enviar backlog reciente y nuevos eventos sin depender de un store externo.

## Resultado después del fix

Comando ejecutado:

- `timeout 3s curl -iN http://127.0.0.1:8000/livetrace2/stream`

Resultado observado:

- `HTTP/1.1 200 OK`
- `content-type: text/event-stream`
- Headers SSE correctos
- Primer chunk inmediato:

```text
: connected
```

Confirmación adicional en consola Uvicorn:

- múltiples `GET /livetrace2/stream ... 200 OK`
- sin traceback durante conexiones SSE

## Nota github.dev (host externo)

No se validó aquí un dominio `github.dev` concreto porque no se proporcionó URL pública exacta en esta sesión.
Aun así, el fix elimina la excepción del backend y añade handshake/keepalive anti-timeout para proxies SSE.
