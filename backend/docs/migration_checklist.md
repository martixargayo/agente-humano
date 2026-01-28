# Migration & Compatibility Checklist

## Compatible y sin cambios de estructura
- [x] Orden del grafo LangGraph intacto (world → belief → precedence → intent → phase → policy_planner → progress → executor).
- [x] Endpoints y contratos externos sin cambios.
- [x] Campos existentes de WorldState/IntentState/PolicyDecision preservados.

## Cambios nuevos (backward compatible)
- [x] WorldState añade `evidence_items`, `world_state_meta`, `deadline_days`, `deadline_kind`, `urgency_reason`, `tone_confidence`, `conflict_markers`.
- [x] IntentState añade contadores de progreso (`no_progress_turns`, `slot_fill_count`, `slot_fill_count_recent`).
- [x] Policy añade contrato explícito (`required_inputs`, `target_slots`, `expected_effects`, `failure_modes`) y reglas duras estructuradas.
- [x] Validator post-respuesta con reparación controlada.

## Defaults conservadores
- [x] Umbrales vía env con defaults seguros (`EVIDENCE_CONFIDENCE_MIN=0.6`, `INTENT_*`).
- [x] Si no hay evidencia, comportamiento similar al legacy.

## Tests añadidos/actualizados
- [x] Señales débiles vs fuertes (firmness, deadline).
- [x] Dedupe de evidencias.
- [x] Abort por no progreso.
- [x] Validator con reparación.
- [x] Catálogo policies incluye nuevos campos.
