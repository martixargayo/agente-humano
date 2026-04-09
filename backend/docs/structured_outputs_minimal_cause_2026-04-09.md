# Structured Outputs — hipótesis mínima más fuerte (2026-04-09)

## Hallazgo técnico central (antes del fix)
En `BrainOutput`, el nodo:

`$defs.BrainStatePatch.properties.memory_episodic_append.items`

es de tipo `object` con:

`additionalProperties: {"type": "string"}`

(no `false`).

Eso violaba la regla de Structured Outputs strict en OpenAI para objetos con `additionalProperties: false` y explicaba por qué el provider podía rechazar el schema con mensajes no intuitivos.

## Estado tras fix de contrato
Se reemplazó el item libre por un modelo tipado y cerrado (`BrainStatePatch.MemoryEpisodicAppendItem`), por lo que:
1. `memory_episodic_append.items` ahora expone `properties` + `required` + `additionalProperties: false`.
2. `validate_openai_structured_output_subset` ya no reporta esa violación para `BrainOutput`.
3. El flujo vuelve a intentar provider call (sin hard-fail por este punto).

## Estado de replay real
Scripts listos para ejecutar contra OpenAI real:
- `backend/scripts/replay_structured_output_request.py`
- `backend/scripts/reduce_brain_schema_against_openai.py`

En este entorno no hay `OPENAI_API_KEY`, por lo que el replay real queda pendiente de ejecución en entorno con credenciales.
