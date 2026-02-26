# P0 — Ledger Sync Execution Plan (planner/executor)

## 1) Síntoma + referencia LiveTrace
- Caso crítico observado (Turno 12): `world_judge_llm` produce `semantic_ledger` poblado, pero `planner_llm` ve `SEMANTIC_LEDGER_JSON` vacío y `executor_llm` lo ve poblado.
- Referencia de diagnóstico: `../01_semantic_ledger_desync_planner_executor.md`.

## 2) Objetivo / Definition of Done
**Objetivo:** planner y executor deben consumir exactamente el mismo `effective_semantic_ledger` en el mismo turno.

**DoD**
- `ledger_mismatch_rate` planner vs executor = `0%` en replay.
- En LiveTrace2: `planner_ledger_hash == executor_ledger_hash` por turno.
- Sin añadir validadores bloqueantes ni reglas duras en runtime conversacional.

## 3) Propuesta (prompting + mínimo plumbing)
> Esta solución es **plumbing de contexto mínimo**, no heurística conversacional.

### 3.1 Cambios mínimos de contexto/pipeline
- Introducir una única vista de turno: `effective_semantic_ledger`.
- Calcularla una vez después de `world_judge_llm` y antes de renderizar prompts.
- Inyectar la misma vista tanto al planner como al executor.

### 3.2 Cambios de prompt (texto exacto sugerido)
**Planner prompt** (`backend/prompts.py`, `PLANNER_SEMANTIC_V1_USER_PROMPT`) — añadir bloque:

```text
CONSISTENCY_NOTE:
- Usa SEMANTIC_LEDGER_JSON como memoria táctica única de este turno.
- Trata ese ledger como fuente de verdad para evitar repetir ideas ya tratadas.
- No propongas next_move_hint que reabra una idea ya cubierta, salvo que el usuario la reabra explícitamente.
```

**Executor prompt** (`backend/negotiation/elementos/render/executor_prompts.py`, `EXECUTOR_V2_USER_PROMPT`) — añadir bloque:

```text
CONSISTENCY_NOTE:
- SEMANTIC_LEDGER_JSON ya está reconciliado para este turno.
- Prioriza coherencia con ese ledger por encima de hábitos genéricos de repreguntar.
- Si el usuario trae algo ya tratado, valida y avanza sin repetir la misma idea.
```

## 4) Ejemplos antes/después
### Antes (drift)
- Planner sugiere: “¿Cómo lo has mantenido estos años?”
- Executor pregunta mantenimiento otra vez.

### Después (sync)
- Planner sugiere: “Valida mantenimiento ya explicado y pasa a siguiente frente útil.”
- Executor: “Perfecto, me queda claro el mantenimiento. Si te parece, pasamos a revisar expectativas de cierre.”

## 5) Plan de pruebas (replay) + métricas
- Replay de conversaciones con eventos donde el judge actualiza ledger en medio del turno.
- Métrica técnica: hash planner/executor del ledger por turno.
- Métrica semántica (LLM-judge): reducción de repreguntas sobre ideas ya cubiertas.
- Sin checks por keyword; evaluación por intención conversacional.

## 6) Riesgos y tradeoffs
- Si el judge falla y ledger degradado se propaga, ambos nodos serán coherentes pero “coherentemente pobres”.
- Mitigación LLM-first: fallback semántico suave + mejor prompt del judge (no gate duro).

## 7) Checklist implementación futura
- [ ] Definir `effective_semantic_ledger` en estado de turno.
- [ ] Inyectar misma referencia en planner y executor.
- [ ] Añadir hashes de observabilidad en LiveTrace2.
- [ ] Ejecutar replay y confirmar mismatch 0%.
