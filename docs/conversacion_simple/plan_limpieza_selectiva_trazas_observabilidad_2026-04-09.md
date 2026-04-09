# Plan de limpieza selectiva de trazas/observabilidad en `conversacion_simple` (2026-04-09)

## Resumen ejecutivo

El estado actual de `conversacion_simple` conserva observabilidad útil para operación (fallbacks, éxito de modelo, latencia, estado final, métricas de memoria), pero también persiste payloads completos y snapshots de schema pensados para forensics de crisis de Structured Outputs. La recomendación es **mantener una capa compacta always-on**, **reducir bloques pesados** y **mover capturas completas a modo debug/forensic opt-in**.

Criterio aplicado:

1. **Optimización de prompts**: se conserva lo que permite correlacionar calidad de respuesta con contexto y resultado (`final_status`, `fallback_reason_code`, `model_attempted/succeeded`, latencia, conteos de memoria).
2. **Debugging normal / soporte operativo**: se conserva lo mínimo suficiente para responder “qué pasó” sin blobs grandes (modelo objetivo, response_id, razón de fallback, excepción sanitizada, hash de schema, fingerprint de build/deploy).
3. **Forensics de crisis**: se mueve a debug opcional lo que captura request/response o schema completo (alto volumen, alta duplicación, bajo uso continuo).

## Inventario actual y clasificación

### 1) Envelope `ConversationSimpleTurnTrace`

| Campo / bloque | Dónde | Uso histórico | Valor actual | Decisión |
|---|---|---|---|---|
| `turn_id`, `timestamp_utc`, `session_id`, `user_id` | `ConversationSimpleTurnTrace` | Correlación de turnos | Alto (operación) | **mantener** |
| `user_turn`, `final_reply_text`, `final_status` | `ConversationSimpleTurnTrace` | QA funcional y UX | Alto (prompt optimization + soporte) | **mantener** |
| `brain_model_attempted`, `brain_model_succeeded`, `brain_fallback_reason_code` | `ConversationSimpleTurnTrace` | Diagnóstico de caídas/fallback | Alto | **mantener** |
| `stage_timings_ms` (hoy `brain_call`) | `ConversationSimpleTurnTrace` | Performance básica | Alto | **mantener** |
| `context_id` | `ConversationSimpleTurnTrace` | Paridad inter-contexto | Alto | **mantener** |
| `runtime_version` | `ConversationSimpleTurnTrace` | Correlación deploy/runtime | Alto en producción | **mantener** |
| `conversation_id_*`, `previous_response_id_*` | `ConversationSimpleTurnTrace` | Rastreo provider threading | Medio (útil si se usa threading provider) | **reducir** (dejar solo `response_id` efectivo) |
| `nodes` (solo `brain`) | `ConversationSimpleTurnTrace` | Contrato de nodos + debugging | Medio/alto | **mantener** |
| `memory_observability` | `ConversationSimpleTurnTrace` | Bloque principal de telemetría | Alto pero sobredimensionado | **reducir** |

### 2) `nodes.brain`

| Campo / bloque | Dónde | Uso histórico | Valor actual | Decisión |
|---|---|---|---|---|
| `node_name`, `status`, `latency_ms` | `nodes.brain` | Estado y latencia por nodo | Alto | **mantener** |
| `model_called`, `model_attempted`, `model_succeeded` | `nodes.brain` | Diferenciar fallback antes/después de llamada | Alto | **mantener** |
| `fallback_reason_code` | `nodes.brain` | Diagnóstico de degradación | Alto | **mantener** |
| `input_summary.recent_dialogue_count` | `nodes.brain` | Context pressure debugging | Medio (útil y compacto) | **mantener** |
| `output_summary.memory_episodic_append_count` | `nodes.brain` | Deriva de memoria por turno | Medio/alto | **mantener** |
| `output_summary.provider_exception` (duplicado) | `nodes.brain` y `memory_observability` | Forensics de provider | Medio, pero redundante | **reducir** (dejar solo un punto canónico) |

### 3) `memory_observability` (resumen útil)

#### Mantener (always-on)
- `brain_model_attempted`, `brain_model_succeeded`, `brain_fallback_reason_code`.
- Métricas de trimming: `memory_recent_dialogue_count_before/after/trimmed_count`.
- Métricas de compacción: `memory_compaction_scheduled/mode/status/reason`, `memory_compacted_summary_chars_before/after`, `memory_growth_anomaly_flag`.
- Conteos de archivado: `memory_summary_archived_turns`, `memory_summary_archived_messages`.
- Fuente de compacción: `memory_summary_compaction_source`.

#### Reducir
- `memory_post_assistant_archived_turns`: útil pero secundaria; puede consolidarse dentro de un resumen único de archivado por turno.

#### Mover a debug/forensic
- `brain_provider_exception` completo (mantener en always-on una versión mínima: tipo/código/status).
- `summarizer_provider_exception` completo (mismo criterio).

### 4) Provider request/response/schema fingerprint

| Campo / bloque | Dónde | Uso histórico | Valor actual para prompts | Decisión |
|---|---|---|---|---|
| `brain_provider_request` | `memory_observability` | Validar payload real vs SDK/HTTP en crisis | Bajo para prompts; alto costo | **mover a debug/forensic** |
| `brain_provider_response_text` | `memory_observability` | Forensics de parseo JSON | Bajo para prompts; riesgo de volumen/PII | **mover a debug/forensic** |
| `summarizer_provider_request` | `memory_observability` | Igual que brain | Bajo continuo | **mover a debug/forensic** |
| `summarizer_provider_response_text` | `memory_observability` | Igual que brain | Bajo continuo | **mover a debug/forensic** |
| `brain_schema_observability` | `memory_observability` | QA de schema strict | Medio | **reducir** (dejar hash + valid + first_mismatch) |
| `summarizer_schema_observability` | `memory_observability` | QA de schema strict | Medio | **reducir** |
| `brain_runtime_fingerprint.schema_serialized` | `memory_observability` | Snapshot completo del schema enviado | Muy bajo para operación/prompts; alto peso | **eliminar** de always-on (debug opt-in) |
| `summarizer_runtime_fingerprint.schema_serialized` | `memory_observability` | Idem | Muy bajo | **eliminar** de always-on (debug opt-in) |
| `*_runtime_fingerprint` compacto (model target, format name/strict, schema_hash, first_mismatch, build/deploy versions) | `memory_observability` | Correlación técnica compacta | Alto | **mantener** |
| `root_properties/root_required/brain_state_patch_*` detallados | `*_runtime_fingerprint` | Forensics fine-grained de schema | Bajo/medio | **reducir** (mantener como máximo top-level counts + hash) |

## Criterio estricto de optimización de prompts

Campos que **sí** ayudan a iterar prompts:
- `final_status` (`deliver/clarify/refuse`),
- `final_reply_text` (o resumen textual derivado),
- contexto (`context_id`),
- `brain_fallback_reason_code`,
- `model_attempted/succeeded`,
- latencia,
- conteos de memoria (presión de contexto/compacción).

Campos que **no** ayudan de forma sostenida a optimización de prompts:
- payload raw completo al provider,
- respuesta raw completa del provider,
- schema serializado completo en cada turno,
- huellas forenses demasiado detalladas cuando ya existe `schema_hash` + `valid` + `first_mismatch`.

## Recomendación concreta de limpieza (mínima y segura)

### Quitar ya (always-on)
1. `brain_runtime_fingerprint.schema_serialized`.
2. `summarizer_runtime_fingerprint.schema_serialized`.

### Reducir
1. `brain_schema_observability` y `summarizer_schema_observability` a vista compacta:
   - `schema_name`, `schema_hash`, `validation.valid`, `validation.first_mismatch`, `openai_subset_validation.valid`, `openai_subset_validation.first_violation`.
2. `*_runtime_fingerprint`:
   - mantener build/runtime/model/format/schema_hash/first_mismatch,
   - reemplazar listas de propiedades por contadores (`root_properties_count`, etc.).
3. deduplicar `provider_exception` (canónico en `memory_observability` o en `nodes.brain`, no en ambos).

### Mover a modo `debug/forensic` opcional
1. `brain_provider_request`, `summarizer_provider_request`.
2. `brain_provider_response_text`, `summarizer_provider_response_text`.
3. snapshots completos de schema u observabilidad extendida.

### Dejar igual
- Envelope de traza funcional.
- Semáforos operativos de fallback/success.
- timings.
- métricas de memoria compactas.
- fingerprint de runtime/deploy compacto.

## Riesgos de limpiar de más

1. **Si se elimina `fallback_reason_code`**: se pierde diagnóstica de degradación por clase de fallo.
2. **Si se elimina `runtime_version`/fingerprint**: se dificulta correlación por réplica/deploy.
3. **Si se elimina toda observabilidad de schema**: reaparece ceguera ante regresiones de compatibilidad strict-schema.
4. **Si se elimina `final_status` o métricas de memoria**: cae capacidad de optimizar prompts con evidencia contextual.

## Plan de implementación sugerido

### Tanda 1 (segura, bajo riesgo)
- Objetivo: adelgazar storage sin cambiar semántica de ejecución.
- Cambios:
  1. Quitar `schema_serialized` de `_provider_runtime_fingerprint`.
  2. Introducir versión compacta de `schema_observability` al persistir en `memory_observability`.
  3. Mantener contratos de campos críticos actuales.

### Tanda 2 (controlada con flag)
- Objetivo: mover forensics pesados a modo opt-in.
- Cambios:
  1. Flag `CONVERSACION_SIMPLE_TRACE_FORENSIC=1` (o config equivalente).
  2. Persistir request/response raw solo con flag.
  3. Añadir tests de contrato para modo normal vs modo forensic.

## Archivos candidatos a tocar (cuando se implemente)

- `backend/conversacion_simple/orchestration/pipeline.py`
  - ensamblado de `memory_observability`, runtime fingerprint y payloads raw.
- `backend/conversacion_simple/traces/builders.py`
  - posible deduplicación de `provider_exception`.
- `backend/tests/test_conversacion_simple_clean_wiring.py`
- `backend/tests/test_conversacion_simple_phase2_runtime.py`
- `backend/tests/test_conversacion_simple_phase4_memory.py`
  - actualizar expectativas de contratos de observabilidad (modo normal y forensic).

## Conclusión

`conversacion_simple` ya no está en fase de crisis. El diseño recomendado es:

- **always-on compacto y operativo**,
- **forensics pesado bajo demanda**,
- sin perder señales críticas para prompts ni para soporte.

Esto reduce costo/ruido y conserva capacidad real de diagnóstico en producción.
