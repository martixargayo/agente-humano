# Documento 4 — LiveTrace2: añadir el finalizer como elemento

## Objetivo
Agregar el finalizer como elemento visible y trazable en LiveTrace2 con formato consistente con los nodos actuales.

## Ubicación en secuencia
1. Mantener orden actual de nodos.
2. Insertar nuevo elemento inmediatamente después de `executor`.
3. Nombre recomendado y consistente: `executor_finalizer_llm`.

## Requisitos de visualización
1. Debe aparecer en la lista de elementos con el mismo estilo de línea que el resto.
2. Debe incluir timestamps, latencia y estado (`ok/error`) igual que otros eventos LLM.
3. Debe conservar truncado/hash de payload según política existente de trace.

## Campos mínimos de telemetría para debug
1. `finalizer_called` (bool)
2. `finalizer_changed_from_draft` (bool)
3. `finalizer_fixes` (lista)
4. `latency_ms_finalizer` (int)

## Campos recomendados adicionales
1. `finalizer_model`
2. `finalizer_tokens_in`
3. `finalizer_tokens_out`
4. `finalizer_schema_valid` (bool)
5. `finalizer_mode` (`shadow|active`)

## Fuente de datos por etapa
1. Antes de finalizer: snapshot de `executor_draft_json`.
2. Después de finalizer: snapshot de `executor_final_json`.
3. Diff funcional mínimo:
   - cambio en `response_text`
   - cambio en `asked_question`
   - cambio en `requested_info_slots`

## Criterio de cierre LiveTrace2
1. El nuevo elemento aparece siempre que el flag esté activo.
2. El nuevo elemento no rompe orden ni render de nodos previos.
3. Los cuatro campos de debug solicitados quedan visibles en cada turno.
