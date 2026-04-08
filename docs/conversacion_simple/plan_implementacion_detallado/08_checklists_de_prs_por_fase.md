# 08 · Checklists de PR por fase

## Fase 1 — PR de esqueleto y contratos

### Debe incluir
- Nuevo paquete `backend/conversacion_simple/` con submódulos base.
- Context resolver/binding/public mapping del nuevo flow.
- Canonical state base y config base.
- Contextos iniciales `baseline` y `negociacion_sala_reuniones` equivalentes.
- Tests de resolver/binding/schema/context assets.

### NO debe incluir
- Runtime LLM de turno.
- Cambios en endpoints/superficies.
- Cambios en optimizador.
- Compresión/memoria diferida.

### Tests mínimos
- `test_conversacion_simple_context_resolution`
- `test_conversacion_simple_context_binding`
- `test_conversacion_simple_assets_schema`
- `test_conversacion_simple_canonical_state_defaults`

### Qué revisar (reviewers)
- **Arquitectura:** consistencia de contratos con docs decisionales.
- **Backend runtime:** no tocar `negociacion`.
- **QA:** cobertura de casos de conflicto de contexto.

### Evidencias para aprobar
- PR acotada a esqueleto.
- Todos los tests de fase en verde.

---

## Fase 2 — PR de runtime 1-LLM

### Debe incluir
- Implementación de `BrainInput/BrainOutput`.
- Runtime de turno con una sola llamada LLM.
- Aplicación de `state_patch` determinista.
- Trace single-node con guardrails.
- Tests de single-call y contrato de salida.

### NO debe incluir
- Integración de superficies IU/optimizador.
- Mecanismo de compresión diferida completo.

### Tests mínimos
- `test_conversacion_simple_single_llm_path`
- `test_conversacion_simple_brain_output_contract`
- `test_conversacion_simple_state_patch_determinism`
- `test_conversacion_simple_trace_contract`

### Qué revisar (reviewers)
- **Runtime:** garantía real de 1 llamada.
- **Seguridad/guardrails:** paridad de decisiones de bloqueo/rewrite.
- **Observabilidad:** trace consumible.

### Evidencias para aprobar
- Prueba automatizada de una sola invocación LLM por turno.
- No regresión en subset `negociacion`.

---

## Fase 3 — PR de superficies/contextos/tooling

### Debe incluir
- Routing flow-aware en IU y optimizador.
- Soporte completo de contextos iniciales en superficies.
- Adaptación de trace_reader/compare_turns para single-node.
- Tests E2E y mixed-flow.

### NO debe incluir
- Endurecimiento final de compresión diferida.
- Tuning avanzado de memoria larga.

### Tests mínimos
- E2E IU (`bootstrap/turn/finalize`) con contexto `conversacion_simple`.
- E2E optimizador sandbox/compare/list_contexts/list_prompts.
- Tests de invariantes externas obligatorias.

### Qué revisar (reviewers)
- **API owner:** compatibilidad externa.
- **Tooling owner:** no ruptura de lectura de traces.
- **Product owner:** equivalencia externa validada.

### Evidencias para aprobar
- Matriz compatibilidad 12 validada punto a punto.
- `negociacion` sigue funcional.

---

## Fase 4 — PR de memoria/compresión/endurecimiento

### Debe incluir
- Trimming determinista de `recent_dialogue`.
- Trigger/scheduling de compresión diferida.
- Ejecución diferida mínima + fallback determinista.
- Campos de observabilidad de memoria en trace.
- Tests largos y de fallo/fallback.

### NO debe incluir
- Replanteamiento de arquitectura de runtime.
- Cambios de contrato externo de endpoints.

### Tests mínimos
- long conversation stability
- deferred compaction success/failure
- fallback activation
- growth anomaly detection

### Qué revisar (reviewers)
- **Runtime:** no bloqueo del turno por compresión.
- **Ops:** riesgos de mecanismo diferido.
- **QA:** escenarios largos y degradación controlada.

### Evidencias para aprobar
- Latencia de turno no degradada por compresión.
- Fallback comprobado en tests.
- Métricas observables presentes en trace.

---

## Reglas de gate para todas las fases

1. PR de fase N no debe incluir alcance de fase N+1.
2. Cada PR debe mapear archivos tocados contra `06_mapa_de_archivos_y_funciones.md`.
3. Si aparece cambio no planificado, debe documentarse explícitamente en la PR.
