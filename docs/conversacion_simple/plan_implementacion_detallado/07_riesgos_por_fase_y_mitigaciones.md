# 07 · Matriz de riesgos por fase y mitigaciones

## Fase 1 — Esqueleto/contratos

- **Riesgo técnico principal:** contratos base divergentes de invariantes existentes.
- **Riesgo de drift:** bajo (aún sin surfaces).
- **Riesgo de romper `negociacion`:** muy bajo.
- **Riesgo de falsa compatibilidad:** bajo.
- **Riesgo de tooling:** bajo.
- **Riesgo de tests insuficientes:** medio.
- **Mitigación:** tests de resolver/binding/schema/context contract desde el día 1.
- **Señal de alerta temprana:** discrepancias entre contextos `baseline` y `negociacion_sala_reuniones`.

## Fase 2 — Runtime 1-LLM

- **Riesgo técnico principal:** contrato `BrainOutput` inestable o demasiado grande.
- **Riesgo de drift:** medio.
- **Riesgo de romper `negociacion`:** bajo si aislamiento de namespace.
- **Riesgo de falsa compatibilidad:** medio (trace envelope vs node shape).
- **Riesgo de tooling:** medio.
- **Riesgo de tests insuficientes:** alto si no se valida “single-call”.
- **Mitigación:** tests explícitos de 1 llamada LLM + contract tests + trace tests.
- **Señal de alerta temprana:** aparición de más de una llamada modelo en path de turno.

## Fase 3 — Superficies/contextos/tooling

- **Riesgo técnico principal:** routing flow-aware incorrecto en IU/optimizador.
- **Riesgo de drift:** alto (dos flows activos externamente).
- **Riesgo de romper `negociacion`:** medio.
- **Riesgo de falsa compatibilidad:** alto (API igual, tooling roto).
- **Riesgo de tooling:** alto (`trace_reader`, `compare_turns`).
- **Riesgo de tests insuficientes:** alto si faltan E2E mixed-flow.
- **Mitigación:** matriz de compatibilidad obligatoria + E2E por flow + mixed trace fixtures.
- **Señal de alerta temprana:** errores en optimizador al abrir turnos de `conversacion_simple`.

## Fase 4 — Memoria/compresión/endurecimiento

- **Riesgo técnico principal:** compresión diferida incompleta o inconsistente.
- **Riesgo de drift:** medio.
- **Riesgo de romper `negociacion`:** bajo (aislado) / medio si se tocan utilidades compartidas.
- **Riesgo de falsa compatibilidad:** medio (respuesta ok, memoria degradada silenciosa).
- **Riesgo de tooling:** medio (nuevos campos observables no consumidos).
- **Riesgo de tests insuficientes:** muy alto si no hay escenarios largos/fallo.
- **Mitigación:** tests long-run + fallback drills + alertas de growth anomaly.
- **Señal de alerta temprana:** crecimiento sostenido de memoria sin compresión efectiva.

---

## Riesgos transversales y mitigaciones globales

1. **Duplicación controlada se vuelve duplicación caótica**
   - Mitigación: checklists por fase, PRs acotadas, reviewers específicos.
2. **Regresión oculta en `negociacion`**
   - Mitigación: correr subset de regresión `negociacion` en todas las fases.
3. **Ambigüedad de ownership de contratos**
   - Mitigación: ADR + matriz compatibilidad como documentos normativos.
