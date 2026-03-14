# 12 — Plan de impacto de cambios en el repo (no-ruptura)

## 0) Objetivo

Documentar exactamente qué se crea y qué se toca para implementar evaluación sin romper negociación ni `interfaz_usuario`.

## 1) Archivos nuevos (por crear)

## Backend evaluación

- `backend/evaluacion/api/*`
- `backend/evaluacion/engine/*`
- `backend/evaluacion/domains/negotiation/*`
- `backend/evaluacion/prompts/*`
- `backend/evaluacion/storage/*`

## Tests evaluación

- `backend/tests/test_feedback_*.py` (unit + integration + contract).

## 2) Archivos existentes a modificar (mínimos)

1. `backend/interfaz_usuario/__init__.py`
   - agregar rutas de feedback.
2. `backend/interfaz_usuario_app/app.js`
   - conectar flujo finalizar→evaluación→polling→reporte.
3. `backend/interfaz_usuario_app/index.html` (si hace falta)
   - contenedores modal/loading/reporte.

## 3) Puntos exactos de cambio

## `interfaz_usuario/__init__.py`

- añadir imports del router de evaluación,
- mantener rutas actuales sin alterar.

## `interfaz_usuario_app/app.js`

- ampliar handler `finishNegotiationBtn.onclick`.
- añadir funciones `startEvaluation`, `pollEvaluation`, `renderFeedbackReport`.
- no tocar `send.onclick` salvo acoplamiento visual del estado de cierre.

## 4) Zonas protegidas (NO tocar)

- `backend/negociacion/orchestration/*`
- `backend/negociacion/nodes/*`
- `backend/negociacion/guards/*`
- `backend/negociacion/pipeline.py`
- `backend/api/app.py` en flujo conversacional existente, salvo inclusión de router ya encapsulado.

## 5) Por qué no rompe sistema actual

1. Evaluación se ejecuta en endpoint independiente.
2. No modifica contratos de turnos ni canonical state operativo.
3. No introduce trabajo síncrono adicional en cada turno.
4. Fallo de evaluación no afecta continuidad del chat histórico.

## 6) Cambios mínimos recomendados por fase

- Fase backend: añadir módulos nuevos sin editar negociación.
- Fase frontend: añadir modal/loading/report con feature flag local si se desea rollout progresivo.
- Fase QA: ejecutar regresión de turnos y finish button.

## 7) Criterios de aceptación de no-ruptura

- `/api/interfaz_usuario/negociacion/turn` mantiene respuesta y comportamiento.
- `finish_button_armed` sigue armándose con reglas actuales.
- flujo de evaluación solo se activa tras confirmación de finalizar.
- si evaluación falla, UI vuelve a estado estable sin bloquear app.

## 8) Riesgos de impacto y mitigación

- Riesgo: mezclar lógica de evaluación con envío de turnos.
  - Mitigación: encapsular evaluación en módulo/hook separado.
- Riesgo: tocar estado compartido de sesión durante evaluación.
  - Mitigación: trabajar sobre snapshots congelados (read-only).
- Riesgo: regresión UI por reutilizar demo hardcodeada.
  - Mitigación: render estrictamente desde `ui_feedback_report_v1`.
