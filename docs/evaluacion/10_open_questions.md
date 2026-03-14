# 10 — Preguntas abiertas, decisiones cerradas y tradeoffs

## 1) Decisiones cerradas (NO reabrir)

1. Evaluador del desempeño del usuario (no del agente).
2. Pipeline post-cierre, aditivo al flujo de conversación.
3. Contratos v1: bundle + core + trajectory + ui report.
4. Structured outputs strict.
5. Reconciliación backend entre salidas.
6. Base analítica: diálogo; trazas mínimas/defensivas.
7. Persistencia separada de canonical state.
8. Modelos v1 fijados:
   - core: `gpt-5.4`
   - trajectory: `gpt-5.4`
9. Integración sin modificar lógica de turnos en caliente.

## 2) Preguntas abiertas reales

1. ¿Durabilidad en v1.1: SQLite o Postgres directa?
2. ¿Número final de reintentos transitorios por runner (1 vs 2)?
3. ¿SLA UX formal por entorno (local/staging/prod)?
4. ¿Política de versiones de reporte por sesión (última activa vs múltiples)?

## 3) Tradeoffs documentados

## In-memory v1 vs durable inmediato

- v1 in-memory reduce riesgo de tocar piezas sensibles.
- durable inmediato mejora recuperación tras restart.
- decisión: in-memory v1 + interfaz de repositorio para migración.

## Reconciliación estricta vs tolerancia

- estricta evita informes inconsistentes,
- tolerancia limitada evita fallos innecesarios por pequeñas desviaciones.
- decisión: corrección segura acotada + hard-fail cuando hay inconsistencia estructural.

## 4) Señales de implementación fuera de scope (no mezclar en v1)

- recalibración automática continua de scoring,
- uso intensivo de trazas internas,
- cambiar pipeline de negociación para “ayudar” al evaluador.

## 5) Checklist de salida a implementación

- [ ] contratos y reconciliación aprobados,
- [ ] prompts plantillados y versionados,
- [ ] plan de cambios de repo validado (`12_repo_change_impact_plan.md`),
- [ ] criterios de no-ruptura de `interfaz_usuario` aceptados,
- [ ] tests mínimos definidos y priorizados.
