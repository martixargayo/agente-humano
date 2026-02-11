# Negotiation model configuration (Single Source of Truth)

El módulo `backend/negotiation/config/models.py` centraliza **todos** los modelos y parámetros ajustables del módulo de negociación.

## Precedencia

1. **Request override en código** (`get_negotiation_model_config(overrides=...)`)
2. **Variables de entorno** (`NEGOTIATION_*`)
3. **Defaults en código** (SoT)

## Variables recomendadas

### Modelos
- `NEGOTIATION_WORLD_MODEL` (default: `gpt-4.1-nano`)
- `NEGOTIATION_BELIEF_MODEL` (default: `gpt-4.1-nano`)
- `NEGOTIATION_PLANNER_MODEL` (default: `gpt-4.1-nano`)
- `NEGOTIATION_SUMMARY_MODEL` (default: `gpt-4.1-nano`)
- `NEGOTIATION_EXECUTOR_MODEL` (default: `gpt-5-nano`)
- `NEGOTIATION_EMBEDDINGS_MODEL` (default: `text-embedding-3-small`)

### Parámetros por componente
Para `WORLD`, `BELIEF`, `PLANNER`, `SUMMARY`, `EXECUTOR`:
- `NEGOTIATION_<COMPONENT>_TEMPERATURE`
- `NEGOTIATION_<COMPONENT>_MAX_TOKENS`
- `NEGOTIATION_<COMPONENT>_TIMEOUT_S`
- `NEGOTIATION_<COMPONENT>_TOP_P`
- `NEGOTIATION_<COMPONENT>_PRESENCE_PENALTY`
- `NEGOTIATION_<COMPONENT>_FREQUENCY_PENALTY`
- `NEGOTIATION_<COMPONENT>_RETRIES`
- `NEGOTIATION_<COMPONENT>_SEED`

Executor adicional:
- `NEGOTIATION_EXECUTOR_REASONING_EFFORT` (default: `minimal`)

Shared:
- `NEGOTIATION_RAG_DIR`

## Compatibilidad backward

Se mantienen env vars legacy como fallback (por ejemplo `WORLD_EXTRACTOR_MODEL`, `BELIEF_MODEL_NAME`, `PHASE_POLICY_MODEL_NAME`, `SUMMARY_MODEL_NAME`, `EXECUTOR_MODEL_NAME`, `EMBEDDINGS_MODEL_NAME`, `OPENAI_MODEL_NAME`).

Cuando se usan, el sistema registra warning de deprecación con la variable nueva recomendada.

## Cómo cambiar modelos/parámetros

1. Cambia env vars `NEGOTIATION_*` en `.env` (sin tocar secrets como `OPENAI_API_KEY`).
2. O usa overrides en código para una request concreta con `get_negotiation_model_config(overrides=...)`.
3. Revisa `debug_trace` del turno: incluye `models_effective` y `params_effective`.
