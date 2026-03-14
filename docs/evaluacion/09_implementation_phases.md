# 09 — Fases de implementación

## Fase 1 — Contratos, shaping y plan de impacto

- cerrar contratos v1,
- implementar tabla de shaping bundle→runners,
- validar plan de cambios mínimos del repo.

Salida: blueprint sin ambigüedad y sin riesgo de contaminación del flujo actual.

## Fase 2 — Backend mínimo no intrusivo

- crear `backend/evaluacion/` base,
- repositorio in-memory + job states,
- endpoints create/status/report con reporte mock.

Criterio: no regresión de endpoints de negociación.

## Fase 3 — Runners LLM reales

- freeze + bundle real,
- core/trajectory con `gpt-5.4`,
- validación strict + reconciliación,
- provenance completo.

Criterio: reporte real consistente o fallo explícito trazable.

## Fase 4 — Integración frontend aditiva

- modal confirm,
- loading + polling,
- render de `ui_feedback_report_v1`.

Criterio: chat sigue igual; evaluación funciona post-cierre.

## Fase 5 — Calidad continua

- suite tests completa,
- datasets fixture/e2e,
- calibración humana periódica,
- ajustes de prompt/rúbrica sin romper contrato.

## Riesgos y mitigación

1. Inconsistencia entre salidas LLM
   - mitigación: reconciliación obligatoria + hard-fail selectivo.
2. Exceso de input por trazas
   - mitigación: trace_digest mínimo y opcional.
3. Regresiones en interfaz_usuario
   - mitigación: cambios mínimos aislados + pruebas de no-ruptura.
