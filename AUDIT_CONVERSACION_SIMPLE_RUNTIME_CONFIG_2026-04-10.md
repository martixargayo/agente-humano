# Auditoría de configuración real (`conversacion_simple`) — 2026-04-10

Este documento consolida hallazgos verificables en código sobre la configuración efectiva del provider para `conversacion_simple`.

## Hallazgos clave

- Modelo principal (brain): `gpt-5.4`.
- Modelo summarizer: `gpt-5.4-nano`.
- Ambos llamados a `responses.create` usan:
  - `text.format` con `json_schema` estricto.
  - `reasoning.effort` explícito (`low` en brain, `minimal` en summarizer).
  - `store=False`.
- No se envían explícitamente: `temperature`, `top_p`, `max_output_tokens`, `service_tier`, `stream`, `previous_response_id`, `prompt_cache_key`, `tools`, `parallel_tool_calls`, `truncation`, `metadata`, `user`.
- `conversacion_simple` no enlaza turnos con estado OpenAI (no usa `previous_response_id` de entrada), aunque sí guarda `response_id` en traza (`previous_response_id_after`).

## Cadena de resolución resumida

1. Entrada HTTP: `POST /api/interfaz_usuario/negociacion/turn`.
2. Enrutado a `interfaz_usuario.services.run_turn`.
3. Si flujo es `conversacion_simple`, construye config con `build_conversacion_simple_pipeline_config(..., stateful=True)`.
4. Ejecuta `run_conversacion_simple_turn`.
5. En pipeline:
   - carga prompts por contexto,
   - potencialmente ejecuta summarizer si hay `archived_turns`,
   - ejecuta brain estructurado,
   - persiste trazas y estado.

## Payload efectivo

### Brain

```python
{
  "model": model,
  "input": messages,
  "text": {
    "format": {
      "type": "json_schema",
      "name": "BrainOutput",
      "schema": normalized_schema,
      "strict": True,
    }
  },
  "reasoning": {"effort": "low"},
  "store": False,
}
```

### Summarizer

```python
{
  "model": model,
  "input": messages,
  "text": {
    "format": {
      "type": "json_schema",
      "name": "SummarizerOutput",
      "schema": normalized_schema,
      "strict": True,
    }
  },
  "reasoning": {"effort": "minimal"},
  "store": False,
}
```

## Continuidad entre turnos

- `ConversationSimpleTurnTrace` define `conversation_id_*` y `previous_response_id_*`.
- En runtime solo se setea `previous_response_id_after=call.response_id`.
- No hay uso de `previous_response_id` al llamar al provider en brain/summarizer.

Conclusión: continuidad OpenAI server-side no está activa para `conversacion_simple`.
