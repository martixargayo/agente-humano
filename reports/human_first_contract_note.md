# Nota técnica: contrato “respuesta humana primero, plan después”

## Resumen del contrato

1. **Desvío humano compatible (sin replan):**
   - responder primero en 1-2 frases humanas,
   - hacer puente para retomar,
   - cerrar con la pregunta del step (máx. 1 pregunta).

2. **Cambio explícito de objetivo (con replan):**
   - `world_judge` debe marcar `interrupted_replan` con evidencia,
   - `skip_planner=false`,
   - planner replanifica.

## Wiring aplicado

- `advisor_recs` ahora incluye campos opcionales de human-first (`human_mode`, `answer_focus`, `bridge`, `dont_do`).
- El prompt del executor siempre recibe `ADVISOR_RECS_JSON`, incluso si planner fue skipped.
- Prompts de advisor/planner/executor/judge incorporan reglas explícitas para este contrato.

## Compatibilidad

- No se añadieron nuevos modelos, nodos ni clasificadores externos.
- Se mantiene el contrato de salida del executor y las validaciones actuales (`max_questions`, cumplimiento de ask/instruction).
