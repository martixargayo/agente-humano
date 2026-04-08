# 07 · Superficies API y contratos — impacto de `conversacion_simple`

## 1) `interfaz_usuario`

## Qué debe permanecer idéntico

- bootstrap/turn/finalize/new_conversation shape.
- lock + TTL + surface ownership.
- response envelope con `entry_contract`, `trace_count`, `conversation_id_*`.

## Qué debería tocarse

1. Selección de flujo en bootstrap (por contexto o flag explícita).
2. Resolver de presentation por contexto del flujo correcto.
3. Builder de turn context con `context_source` equivalente para `conversacion_simple`.
4. Config builder flow-aware (`negociacion` vs `conversacion_simple`).

## 2) `optimizador`

## Qué debe permanecer idéntico

- endpoints de sandbox, clone, compare, overrides y trazas.
- uso de `execute_turn_with_contract`.
- metadatos de intentos y semántica de errores/retry.

## Qué debería tocarse

1. `list_contexts` por flujo.
2. `list_prompts` adaptado a prompt único (`brain_prompt`) + assets equivalentes.
3. `compare_turns` para nodos 1-LLM (diffs de un nodo + state patch).

## 3) Legacy `/negociar`

Opciones:

1. mantener solo para `negociacion` (recomendado corto plazo),
2. crear `/conversar` legacy opcional (no necesario en fase inicial).

## 4) Bootstrap, turn, finalize

### Hechos de sistema actual a preservar

- `ensure_session_surface`
- `ensure_session_context`
- `build_*_turn_context`
- `execute_turn_with_contract`

### Propuesta

Crear homólogos flow-aware para `conversacion_simple` sin romper paths actuales.

## 5) Trazas y `entry_contract`

Mantener:
- `entry_surface`, `entrypoint`, `overrides_applied`, `optimizer_wrapper_used`, `new_conversation`, `clone_used`.

Ampliar con:
- `flow_id` explícito en config snapshot.
- `pipeline_topology`: `single_llm` vs `multi_llm`.

## 6) Context resolution y compatibilidad tooling

- Context resolver debe ser por flujo.
- Tooling de forensics/trace reader debe aceptar ambos memory keys.
- Context mismatches deben mantener reason codes compatibles donde sea posible.

## 7) Respuesta a pregunta clave #6

### ¿Cómo soportar `conversacion_simple` en IU + optimizador sin drift?

Con una capa común de contrato (sesión/contexto/turn_contract/trazas) y adaptadores de flujo en runtime. Las superficies no deben duplicar lógica de negocio por flujo.
