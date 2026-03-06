# File Snapshot

Original path:
`backend/negociacion/ARCHITECTURE_VALIDATION_REPORT.md`

Snapshot status:
`current`

Language / type:
`markdown`

```markdown
# Architecture Validation Report

## Intervención actual (limitada)

Esta intervención corrige **dos problemas concretos** y regenera snapshots:

1. `TraceMeta` por nodo (antes se reutilizaba el de memory en todos los nodos).
2. Fallback del canónico preservando también `thread_mode` esperado del flujo.
3. Regeneración limpia de `docs/code_snapshot_current/`.

## 1) Corrección de `TraceMeta` por nodo

### Problema previo
El pipeline construía un único `TraceMeta` con:
- `prompt_version_memory`
- `schema_version="memory_input.v1"`
- `model_memory`

Y lo enviaba también a phase/planner/executor, dejando trazabilidad de payload incorrecta.

### Corrección aplicada
Ahora se crean y cablean **cuatro** metas explícitos por turno:
- `memory_trace_meta`
- `phase_trace_meta`
- `planner_trace_meta`
- `executor_trace_meta`

Con valores correctos por nodo (mismo `turn_id`, pero `prompt_version`, `schema_version`, `model_target` propios).

Se definió constante explícita para input de phase classifier:
- `PHASE_CLASSIFIER_INPUT_SCHEMA_VERSION = "phase_classifier_input.v1"`

## 2) Corrección de fallback canónico con `thread_mode`

### Problema previo
Si `load_state()` fallaba por estado corrupto/inválido, el fallback reconstruía canónico sin respetar de forma explícita el `thread_mode` esperado por el flujo.

### Corrección aplicada
- `StateRepository.load_state(...)` ahora recibe `thread_mode` esperado.
- El fallback `_default_canonical_state(...)` se invoca con ese `thread_mode`.
- El pipeline pasa `config.thread_mode_default` al cargar estado.

Resultado:
- si el flujo usa `conversation`, fallback reconstruye en `conversation`.
- si el flujo usa `previous_response_id`, fallback reconstruye en `previous_response_id`.

Además se mantiene preservación de identidad (`session_id`, `user_id`).

## 3) Tests añadidos/ajustados

Archivo actualizado:
- `backend/tests/test_negotiation_architecture_clean.py`

Cobertura nueva específica:

1. `TraceMeta` por nodo
- verifica payload `trace_meta` correcto para memory/phase/planner/executor.
- verifica que phase/planner/executor **no heredan** valores de memory.

2. Fallback con `thread_mode`
- fallback corrupto en `conversation` conserva modo.
- fallback corrupto en `previous_response_id` conserva modo.
- se preservan `session_id`/`user_id`.

3. E2E mínimo combinado
- estado corrupto + config `previous_response_id`.
- canónico reconstruido en `previous_response_id`.
- payloads de los 4 nodos con `trace_meta` por nodo y schema correcto.

## 4) Regeneración de snapshots

Se eliminó y regeneró completamente:
- `docs/code_snapshot_current/`

El índice y archivos snapshot ahora reflejan el estado exacto post-intervención.

## Hueco real pendiente

Sigue pendiente (ya marcado en código) la política final de selección/deduplicación de memoria episódica.

No se introdujeron shims ni compatibilidad fake para ocultarlo.

```
