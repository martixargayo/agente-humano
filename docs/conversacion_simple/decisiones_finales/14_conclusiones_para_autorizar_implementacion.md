# 14 · Conclusiones para autorizar implementación

## 1) Decisiones cerradas

1. **Arquitectura principal:** Opción A adoptada (`conversacion_simple` como flujo nuevo real).
2. **Compatibilidad externa:** definida por matriz API/session/trace con invariantes obligatorias.
3. **Memoria V1:** 1-LLM online + compresión diferida + fallback determinista.

## 2) Decisiones aún abiertas (no bloqueantes para arrancar fase 1)

1. Mecanismo exacto de ejecución diferida (scheduler/worker concreto).
2. Umbrales numéricos finales de episodic compaction (propuestos, ajustar por pruebas).
3. Nivel de compatibilidad de tooling histórico de optimizador sobre traces mixtas.

## 3) Blockers reales

- No hay blockers de diseño para comenzar implementación por fases.
- Sí hay dependencia de disciplina de pruebas de compatibilidad para evitar drift.

## 4) Recomendación final

✅ **Listo para implementar** siguiendo el plan por fases ya documentado en `docs/conversacion_simple/08_plan_de_implementacion_por_fases.md`, arrancando por fase 0/1 con foco en contratos y esqueleto del flujo.

## 5) Condición de control

Cada PR de implementación debe incluir checklist de:
- invariantes externas obligatorias,
- divergencias internas aceptables,
- ausencia de regresión en `negociacion`.
