# P0 — Deprecar `world_state` en prompts y subir calidad de `world_judge` + `summarizer`

## 1) Síntoma + referencia LiveTrace
- `WORLD_COMPLETO_JSON` llega congelado (`interaction:{}`), `turn_idx` sin valor operativo, y aporta poco a coherencia.
- Referencia base: `../02_world_state_no_avanza_turn_idx_cero.md`.

## 2) Objetivo / Definition of Done
**Objetivo:** dejar de depender de `WORLD_COMPLETO_JSON` y reemplazar su valor por memoria semántica útil: `semantic_ledger` + `MEMORY_LONG`.

**DoD**
- Prompts planner/executor ya no dependen de `WORLD_COMPLETO_JSON` para decisiones conversacionales.
- `semantic_ledger` y `MEMORY_LONG` capturan hechos relevantes y reducen repetición.
- Mejora en `context_relevance_score` (LLM-judge) sin rails rígidos.

## 3) Propuesta centrada en prompting

### 3.1 Qué sacar / deprecar
- Deprecar gradualmente `I) WORLD_COMPLETO_JSON` en `EXECUTOR_V2_USER_PROMPT` (`backend/negotiation/elementos/render/executor_prompts.py`).
- En planner (`backend/prompts.py`), no introducir nuevas dependencias de world state; priorizar ledger y memoria.

### 3.2 Qué reforzar: `world_judge_llm -> semantic_ledger`
**Prompt world judge** (`backend/prompts.py`, `WORLD_JUDGE_V3_USER_PROMPT`) — añadir instrucciones:

```text
SEMANTIC_LEDGER_QUALITY_RULES:
- Captura IDEAS, no frases literales.
- Normaliza en lenguaje breve y útil para conversación futura.
- Prioriza: (a) lo ya tratado, (b) preguntas ya hechas por el asistente,
  (c) temas que el usuario no quiere seguir forzando.
- Evita ruido descriptivo irrelevante; privilegia memoria accionable para el siguiente turno.
```

### 3.3 Qué reforzar: `MEMORY_LONG` (summarizer)
**Summary prompt** (`backend/prompts.py`, `SUMMARY_USER_PROMPT`) — extender con formato semántico:

```text
REGLAS_MEMORIA_LARGA:
- Resume por IDEAS conversacionales útiles para próximos turnos.
- Incluye explícitamente:
  1) hechos relevantes ya acordados o aclarados,
  2) preguntas ya respondidas,
  3) sensibilidad del interlocutor (temas donde insistir molestó),
  4) estado de negociación actual (sin inventar).
- Evita detalle redundante y evita copiar frases literales largas.
```

## 4) Ejemplos antes/después
### Antes (memoria pobre)
- `WORLD_COMPLETO_JSON`: `{ "interaction": {} }`
- `MEMORY_LONG`: resumen genérico sin estado de ideas tratadas.

### Después (memoria útil)
- `semantic_ledger.lo_que_ya_se_toco`: “estado general”, “mantenimiento”, “motivo de venta”.
- `MEMORY_LONG`: “mantenimiento ya explicado; insistir ahí degrada rapport; foco siguiente: rango de cierre.”

## 5) Pruebas replay + métricas (semánticas)
- Replay AB: con world_state en prompt vs deprecado + ledger/summarizer mejorados.
- Métricas:
  - `context_relevance_score` (LLM-judge)
  - `repetition_rate`
  - `ignored_user_question_rate`
- Evaluación por calidad semántica de respuestas, no por keywords.

## 6) Riesgos y tradeoffs
- Riesgo: si summarizer queda débil, perder contexto de largo plazo.
- Mitigación: mejorar prompt de summary y trazabilidad de cobertura semántica en LiveTrace.
- Tradeoff: menos “estado estructurado rígido”, más dependencia de calidad de prompts/modelo.

## 7) Checklist implementación futura
- [ ] Marcar `WORLD_COMPLETO_JSON` como `legacy_optional` en prompts.
- [ ] Mejorar prompt de world_judge para ledger accionable.
- [ ] Mejorar prompt de summarizer para memoria por ideas.
- [ ] Ejecutar replay comparativo y medir mejora semántica.
