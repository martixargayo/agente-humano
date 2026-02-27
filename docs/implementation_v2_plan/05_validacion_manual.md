# Documento 5 — Validación manual

## Objetivo
Validar integración funcional sin harness: comportamiento, memoria, privacidad y robustez contractual.

## Preparación
1. Activar prompts reemplazados como única fuente.
2. Confirmar runtime sin lógica funcional de `NECESITA_INFO`.
3. Ejecutar pruebas en dos modos:
   - sin finalizer
   - con finalizer activo

## Pruebas cortas (3)

### Prueba corta 1 — Anti-asistente y encaje inmediato
1. Escenario: vendedor hace pregunta directa + presión ligera.
2. Esperado:
   - responde primero a la pregunta del vendedor
   - tono humano, no asistente servicial
   - mantiene avance útil en el turno
   - respuesta breve

### Prueba corta 2 — Privacidad y no cesión sin contrapartida
1. Escenario: vendedor pide presupuesto máximo / BATNA.
2. Esperado:
   - no revela cifras sensibles del comprador
   - mantiene límite explícito
   - no concede sin condición recíproca

### Prueba corta 3 — Consistencia táctica con planner
1. Escenario: planner marca `OBJECTIVE_DELTA=test_consistency`, `TACTIC=boundary`.
2. Esperado:
   - executor/finalizer reflejan ese carril táctico
   - no usa preguntas innecesarias
   - conserva coherencia de schema `executor_v2`

## Pruebas largas (2)

### Prueba larga 1 — Drift de personaje (20+ turnos)
1. Escenario: negociación extensa con cambios de tono del vendedor.
2. Esperado:
   - no deriva a “asistente”
   - sostiene agencia del comprador
   - mantiene respuestas compactas
   - evita repetir temas ya cerrados

### Prueba larga 2 — Persistencia de memoria de agencia
1. Escenario: múltiples ciclos de presión/evasivas/transparencia.
2. Esperado en memoria larga:
   - `BOUNDARIES_Y_COMPROMISOS` actualizado
   - `BANDERAS_DEL_VENDEDOR` actualizado
   - `LECCIONES_DE_CONDUCTA` actualizado
   - privacidad respetada (sin cifras sensibles del comprador)

## Checklist de aceptación
1. No aparece `NECESITA_INFO` en rutas activas.
2. No existe gating de preguntas por `need_info_slots`.
3. `next_move_hint` se interpreta por marcador, no por posición.
4. Se observan `objective_delta` y `tactic` en metadata/logs.
5. `requested_info_slots` existe en schema pero no depende del planner.
6. Finalizer (si activo) aparece en LiveTrace2 con campos de debug mínimos.

## Riesgos a vigilar (checklist final)
1. Parseo por posición de línea en vez de marcador.
2. Restos de retry/forced slots de `NECESITA_INFO`.
3. Gating legacy de preguntas por `need_info_slots`.
4. Doble corrección executor+finalizer sin precedencia clara.
5. Prompt activo con wrappers/documentación extra en vez de texto final.
6. Telemetría antigua interpretada como señal funcional.
7. Fallbacks incompletos cuando faltan `OBJECTIVE_DELTA/TACTIC`.
