# 11 · ADR matriz de arquitecturas (decisión cerrada)

## Estado ADR

- **Estado:** Aprobada
- **Fecha:** 2026-04-08
- **Decisión final:** **Opción A adoptada**
- **Alternativa:** Opción B documentada y descartada por ahora

---

## 1) Definición de opciones

### Opción A (adoptada)

**`conversacion_simple` como flujo nuevo real** con estructura propia (contexts/state/orchestration/services), pipeline online 1-LLM y convivencia paralela con `negociacion`.

### Opción B (descartada por ahora)

**Mismo flow base** con topología configurable (`multi_llm` / `single_llm`) dentro de la misma arquitectura de `negociacion`.

---

## 2) Evidencia concreta del repo donde impacta la decisión

### Hechos observados

1. El runtime de `negociacion` está concentrado y acoplado a 4 nodos en `backend/negociacion/orchestration/flow_config.py`.
2. `interfaz_usuario` y `optimizador` ya están estandarizados sobre `execute_turn_with_contract`, por lo que puede coexistir más de un runtime si mantienen ese contrato.
3. El contrato de contexto es robusto y reusable (resolver/session binding/public mapping/precheck) en `backend/negociacion/contexts/*` + `orchestration/turn_context_validator.py`.
4. El shape de trace actual presupone nodos memory/phase/planner/executor; esto tensiona una integración “todo en uno”.

### Rutas de referencia

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/orchestration/turn_contract.py`
- `backend/negociacion/orchestration/turn_context_validator.py`
- `backend/negociacion/contexts/resolver.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/optimizador/services.py`

---

## 3) Matriz comparativa A vs B

## 3.1 Coste de implementación

- **A:** medio/alto inicial (estructura nueva, duplicación controlada).
- **B:** alto de refactor transversal (desacoplar runtime actual sin romper `negociacion`).

**Decisión:** A favorece entrega incremental con menor riesgo sistémico inmediato.

## 3.2 Coste de mantenimiento

- **A:** mayor coste por coexistencia de dos flows (riesgo de drift por duplicación).
- **B:** menor duplicación potencial si el refactor sale bien.

**Decisión:** se acepta mayor coste de mantenimiento inicial en favor de seguridad de evolución.

## 3.3 Riesgo de drift

- **A:** riesgo medio/alto (dos caminos runtime).
- **B:** riesgo medio (un camino único), pero depende de refactor correcto.

**Decisión:** A con mitigación explícita (matriz de compatibilidad + tests espejo + checklist de invariantes).

## 3.4 Riesgo de romper `negociacion`

- **A:** bajo/medio (aislamiento por flow nuevo).
- **B:** medio/alto (refactor intrusivo en runtime vigente).

**Decisión:** A minimiza riesgo de regresión en negocio actual.

## 3.5 Facilidad de rollout

- **A:** alta (activar por flow/contexto).
- **B:** media/baja (rollout mezclado dentro del mismo flow base).

**Decisión:** A es más controlable para activación progresiva.

## 3.6 Claridad conceptual para developers

- **A:** alta (cada flow expresa su topología y contrato).
- **B:** media (una misma base con modos puede volverse opaca).

**Decisión:** A mejora legibilidad operativa en esta etapa.

## 3.7 Coherencia con filosofía priorizada (decisión de negocio)

- **A:** alineada 100% con la directriz ya tomada.
- **B:** reabre discusión de abstracción prematura.

**Decisión:** A.

---

## 4) Ventajas y desventajas honestas

## Opción A — ventajas

1. Aisla impacto de `conversacion_simple`.
2. Reduce probabilidad de romper `negociacion` existente.
3. Permite rollout por flujo/contexto.
4. Permite adoptar 1-LLM sin cirugía del runtime monolítico actual.

## Opción A — desventajas

1. Duplicación de artefactos y lógica (si no se disciplina).
2. Riesgo de drift entre flujos a medio plazo.
3. Mayor carga de documentación y validación cruzada.

## Opción B — ventajas

1. Menos duplicación si se ejecuta impecablemente.
2. Un único runtime teórico para mantener.

## Opción B — desventajas

1. Refactor más arriesgado sobre runtime en producción.
2. Mayor probabilidad de regresión contractual en `negociacion`.
3. Mayor complejidad de rollout y troubleshooting.

---

## 5) Conclusión explícita

- **A = adoptada.**
- **B = descartada por ahora.**

No se reabre la decisión en esta fase.

---

## 6) `por_que_aceptamos_duplicacion_en_esta_fase`

Aceptamos duplicación controlada porque:

1. la prioridad actual es introducir 1-LLM sin poner en riesgo `negociacion`;
2. el sistema tiene contratos externos robustos que se pueden replicar sin cambiar el comportamiento externo;
3. la duplicación se compensa con una política explícita de compatibilidad y suites de tests espejo;
4. el coste de duplicar hoy es menor que el coste/riesgo de un refactor transversal no acotado.

### Condición de aceptación

La duplicación se considera temporalmente válida **solo** si:
- se mantienen invariantes externos,
- se documenta cualquier divergencia interna,
- y se controla drift con pruebas de paridad.
