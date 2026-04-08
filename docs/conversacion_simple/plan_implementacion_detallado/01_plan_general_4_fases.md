# 01 · Plan general de implementación en 4 fases (`conversacion_simple`)

> **Alcance de este documento:** plan operativo de implementación, sin cambios de código en esta fase.

## 0) Premisas cerradas

- `conversacion_simple` será flujo nuevo real.
- Se acepta duplicación controlada vs `negociacion`.
- Invariantes externos deben mantenerse (API/session/context/trace envelope).
- Camino crítico de turno: 1 sola LLM.
- Memoria V1: trimming determinista + compresión diferida + fallback determinista.

Referencias: `docs/conversacion_simple/decisiones_finales/*`.

---

## Fase 1 — Esqueleto de flujo y contratos base

### Objetivo principal
Levantar estructura mínima de `backend/conversacion_simple/` y contratos fundacionales (contextos, estado base, errores/validación equivalentes).

### Resultado esperado
- Resolver de contextos de `conversacion_simple` funcionando.
- Binding de contexto de sesión para el nuevo flujo.
- Modelos base de estado canónico del nuevo flujo.
- Config inicial de flujo sin runtime activo de turno aún.

### Dependencias previas
- Decisiones finales de ADR/compatibilidad/memoria aprobadas.

### Riesgo principal
- Diseñar contratos demasiado distintos a `negociacion` y perder compatibilidad externa futura.

### Impacto esperado en repo
- **Nuevos módulos** en `backend/conversacion_simple/*`.
- **Modificaciones mínimas** en puntos de export/registro, sin activar superficies todavía.

### Áreas tocadas
- Contextos
- Estado
- Contratos/orquestación base
- Tests unitarios de estructura/contrato

### Criterio de finalización
- Suite mínima de tests de resolver/binding/estado en verde.
- No hay cambios en rutas públicas ni runtime de `negociacion`.

### Fuera de fase
- Llamadas LLM reales
- Integración IU/optimizador
- Compresión diferida

---

## Fase 2 — Runtime de turno 1-LLM

### Objetivo principal
Implementar ejecución stateful completa de turno con nodo único `brain` + persistencia + trazas.

### Resultado esperado
- `run_conversacion_simple_turn` funcional.
- `BrainInput/BrainOutput` validados y aplicados de forma determinista.
- Trazas single-node con guardrails.
- Garantía verificable de 1 llamada LLM en camino crítico.

### Dependencias previas
- Fase 1 cerrada (estado/contexts/contracts base).

### Riesgo principal
- Reintroducir accidentalmente lógica multi-llm (directa o indirecta).

### Impacto esperado en repo
- Nuevos archivos de runtime/orquestación en `backend/conversacion_simple`.
- Reuso limitado de utilidades existentes (guardrails/traces) sin tocar runtime `negociacion`.

### Áreas tocadas
- Runtime
- Parser de salida estructurada
- Persistencia de estado
- Trace single-node

### Criterio de finalización
- Tests que prueban una sola llamada de modelo por turno.
- Tests de patch determinista de estado y guardrails.

### Fuera de fase
- Integración de superficies públicas
- Infra de compresión diferida

---

## Fase 3 — Superficies, contextos oficiales y tooling

### Objetivo principal
Conectar `conversacion_simple` a `interfaz_usuario` y `optimizador` manteniendo compatibilidad externa.

### Resultado esperado
- Bootstrap/turn/finalize/new conversation flow-aware.
- Contextos iniciales (`baseline`, `negociacion_sala_reuniones`) activos y equivalentes.
- Tooling de optimizador/trace_reader compatible con traces mixed-flow.

### Dependencias previas
- Fase 2 cerrada.

### Riesgo principal
- Falsa compatibilidad (API igual pero tooling roto por shape interno de traces).

### Impacto esperado en repo
- Cambios controlados en servicios de superficies.
- Nuevos contextos oficiales de `conversacion_simple`.
- Ajustes en modelos/lectores de tooling.

### Áreas tocadas
- Runtime surfaces
- Context assets/presentation
- Tooling de observabilidad

### Criterio de finalización
- E2E en IU y optimizador en verde para `conversacion_simple`.
- Invariantes externas documentadas verificadas.

### Fuera de fase
- Endurecimiento de memoria diferida (solo hooks mínimos si fueran necesarios)

---

## Fase 4 — Memoria/compresión V1 y endurecimiento final

### Objetivo principal
Completar política V1 de memoria: compresión diferida + fallback determinista + observabilidad de crecimiento/anomalías.

### Resultado esperado
- Trigger de compresión operativo.
- Mecanismo diferido mínimo implementado.
- Fallback determinista no bloqueante.
- Métricas/traces para diagnósticos de memoria.

### Dependencias previas
- Fase 3 cerrada (flujo ya utilizable por superficies).

### Riesgo principal
- Complejidad operativa de infraestructura diferida y deriva de resumen en conversaciones largas.

### Impacto esperado en repo
- Nuevos módulos de mantenimiento de memoria en `backend/conversacion_simple`.
- Posibles tareas/script runner internos para job diferido.
- Nuevos tests largos y de fallo/fallback.

### Áreas tocadas
- Memoria
- Observabilidad
- Hardening
- Test de carga conversacional larga

### Criterio de finalización
- Escenarios largos + fallos de compresión + fallback en verde.
- Métricas de crecimiento controlado evidenciadas.

### Fuera de fase
- Optimización avanzada de calidad de resumen (v2+)

---

## Orden recomendado y justificación

1. Fase 1 (base de contratos)
2. Fase 2 (runtime 1-LLM)
3. Fase 3 (superficies/tooling/contextos)
4. Fase 4 (memoria diferida/hardening)

### Por qué este orden

- Evita integrar superficies sobre runtime inestable.
- Reduce riesgo de romper `negociacion` aislando cambios.
- Permite validación incremental de invariantes externas.

---

## Qué NO mezclar en una misma PR

1. **Fase 1 + Fase 2** (evitar activar runtime en PR de esqueleto).
2. **Fase 2 + Fase 3** (evitar debug cruzado runtime+superficies).
3. **Fase 3 + Fase 4** (evitar mezclar compatibilidad externa con tuning de memoria).
4. Cambios de `negociacion` runtime con cualquier fase de `conversacion_simple` (salvo adaptadores puntuales estrictamente necesarios y documentados).
