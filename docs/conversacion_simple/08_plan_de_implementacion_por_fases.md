# 08 · Plan de implementación por fases (sin implementar en esta etapa)

## Fase 0 — Preparación

### Objetivo
Acordar contratos y alcance.

### Entregables
- ADR del flujo `conversacion_simple`.
- Definición de `BrainInput`/`BrainOutput` v1.
- Definición de memory policy (online + diferida).

### Criterio de aceptación
- Aprobación de diseño por revisión humana.

---

## Fase 1 — Esqueleto del flujo

### Objetivo
Crear estructura mínima paralela a `negociacion`.

### Dependencias
Fase 0 aprobada.

### Entregables
- paquete `backend/conversacion_simple/...` (contexts/state/orchestration/services).
- context resolver + session binding + public mapping flow-aware.

### Criterio de aceptación
- tests de resolución/binding/context conflict en verde.

---

## Fase 2 — Runtime 1-LLM

### Objetivo
Implementar turno online con llamada única.

### Entregables
- config builder del flujo.
- ejecución brain node + guardrails + persistencia.
- trace v1 single-node.

### Criterio de aceptación
- `turn` funcional end-to-end con 1 llamada al modelo en camino crítico.

---

## Fase 3 — Memoria y compresión

### Objetivo
Agregar trimming + summarization robusto.

### Entregables
- ventana recent dialogue,
- patch episódico por turno,
- compresión histórica diferida + fallback determinista.

### Criterio de aceptación
- pruebas de conversaciones largas con estabilidad de estado.

---

## Fase 4 — Contextos iniciales

### Objetivo
Publicar `baseline` y `negociacion_sala_reuniones`.

### Entregables
- manifests y assets equivalentes,
- prompts base,
- presentation configs.

### Criterio de aceptación
- tests de equivalencia contractual entre ambos contextos.

---

## Fase 5 — Integración en superficies

### Objetivo
Exponer flujo en `interfaz_usuario` y `optimizador`.

### Entregables
- bootstrap flow-aware,
- turn flow-aware,
- tooling de optimizador compatible.

### Criterio de aceptación
- E2E en ambas superficies sin drift de contratos.

---

## Fase 6 — Tests y validación

### Objetivo
Cerrar huecos de calidad.

### Entregables
- suite unitaria + contrato + assets + e2e + comparativas.

### Criterio de aceptación
- matriz de validación acordada en verde.

---

## Fase 7 — Rollout / activación

### Objetivo
Activación controlada.

### Entregables
- feature flag por flujo/contexto,
- dashboard de métricas latencia/coste/fallos,
- playbook de rollback.

### Criterio de aceptación
- estabilidad en tráfico real de prueba.

---

## Dependencias críticas entre fases

- Fase 2 depende de Fase 1.
- Fase 3 depende de Fase 2.
- Fase 5 depende de Fase 2 y 4.
- Fase 6 depende de todas las anteriores.
- Fase 7 depende de Fase 6.

## Orden recomendado

0 → 1 → 2 → 3 → 4 → 5 → 6 → 7.

## Nota de gestión de riesgo

No mezclar en una sola PR:
- abstracciones transversales,
- runtime nuevo,
- integración superficies,
- y rollout.

Dividir por fases reduce regresiones en `negociacion`.
