# 06 — Plan de fixes por prioridad (propuesta)

## P0 (bloqueantes de coherencia)
1. **Sincronizar ledger para planner/executor en el mismo turno**.
   - Objetivo: eliminar divergencia de `SEMANTIC_LEDGER_JSON` entre nodos.
2. **Corregir avance mínimo de `world_state`**.
   - Objetivo: dejar de emitir `WORLD_COMPLETO_JSON` congelado y `turn_idx=0` perpetuo.

## P1 (calidad conversacional crítica)
3. **Introducir `pending_counterparty_questions` y enforcement human-first**.
4. **Modelar `slot pushback/refusal` para precio**.

## P2 (robustez anti-bucles/repetición)
5. **Guardrails deterministas anti-repregunta** (semantic similarity + canonical intents).
6. **Métricas LiveTrace2 de drift y cumplimiento**.

## Matriz rápida de validación posterior
- KPI1: `% turnos con pregunta directa ignorada`.
- KPI2: `% turnos con repregunta de slot tras pushback`.
- KPI3: `% turnos con mismatch planner_ledger vs executor_ledger`.
- KPI4: `% turnos con world_state_meta.turn_idx monotónico`.
