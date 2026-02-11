# agente-humano
Sistema IA con LangChain para crear un agente humano superrealista

## Deferred summary refresh (negociación)

- `NEGOTIATION_DEFER_SUMMARY=1`: mueve el `summary refresh` fuera del critical path de `/negociar`.
- En este modo, el job se encola al final de `run_negotiation_agent` y opcionalmente también en `/tts` (idempotente por `(user_id, session_id, turn_id)`).
- Por defecto (`0`), se mantiene el comportamiento síncrono actual para una migración segura.
