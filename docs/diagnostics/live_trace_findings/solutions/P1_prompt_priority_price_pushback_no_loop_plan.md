# P1 — Prompt Priority: pushback de precio sin loop

## 1) Síntoma + referencia LiveTrace
- Turno 16: usuario “prefiero que lo digas tú”; respuesta del bot vuelve a preguntar precio.
- Referencia base: `../04_loop_precio_y_pushback_no_persistido.md`.

## 2) Objetivo / Definition of Done
**Objetivo:** tras pushback, evitar repregunta equivalente y avanzar con respuesta humana útil.

**DoD**
- `price_reask_after_pushback_rate` < 5%.
- Incremento de `constructive_progress_after_pushback` (LLM-judge).
- Sin estado rígido de slots ni reglas if/else como enfoque central.

## 3) Propuesta (centrada en prompt changes)

### 3.1 Planner: no repetir la misma jugada tras pushback
**Ruta:** `backend/prompts.py` (`PLANNER_SEMANTIC_V1_USER_PROMPT`).

**Texto exacto sugerido**

```text
PUSHBACK_PRICE_PRIORITY:
- Si el usuario expresa que prefiere que tú digas una cifra/rango,
  evita sugerir como next_move_hint volver a preguntar “qué precio tienes”.
- Prioriza: reconocer su postura + ofrecer rango/oferta prudente o marco de propuesta,
  manteniendo tono colaborativo.
```

### 3.2 Executor: patrón humano (no plantilla rígida)
**Ruta:** `backend/negotiation/elementos/render/executor_prompts.py` (`EXECUTOR_V2_SYSTEM_PROMPT`).

**Texto exacto sugerido**

```text
[PRICE_PUSHBACK — PRIORIDAD CONVERSACIONAL]
- Si el usuario indica “prefiero que lo digas tú” (o equivalente), no repitas la misma pregunta de precio.
- Responde en modo humano:
  1) reconoce su preferencia,
  2) ofrece una referencia prudente (rango/oferta orientativa o criterio claro),
  3) cierra con avance breve y no redundante.
- Mantén flexibilidad; evita respuestas robóticas.
```

## 4) Ejemplos antes/después
### Antes
Usuario: “Prefiero que lo digas tú.”
Asistente: “¿Qué precio tienes en mente?”

### Después (válido A)
Usuario: “Prefiero que lo digas tú.”
Asistente: “Perfecto, te entiendo. Para avanzar con sentido, yo lo movería en un rango prudente según estado y cierre rápido.”

### Después (válido B)
Usuario: “Prefiero que lo digas tú.”
Asistente: “Tiene sentido. Si te parece, te doy una primera referencia razonable y la ajustamos con lo ya comentado.”

## 5) Plan de pruebas (replay) y métricas
- Replay con variantes de pushback explícito/implícito.
- LLM-judge:
  - ¿Repitió la misma pregunta?
  - ¿Respondió de forma colaborativa y útil?
- Métricas:
  - `price_reask_after_pushback_rate`
  - `pushback_response_usefulness_score`
  - `conversation_flow_score`

## 6) Riesgos y tradeoffs
- Riesgo: ofertar demasiado pronto en contextos donde aún falta información.
- Mitigación: permitir “marco/rango prudente” en vez de cifra cerrada cuando aplique.
- Tradeoff: algo menos de extracción de info, más fluidez y progreso real.

## 7) Checklist implementación futura
- [ ] Añadir bloque `PUSHBACK_PRICE_PRIORITY` al planner prompt.
- [ ] Añadir bloque `PRICE_PUSHBACK` al executor prompt.
- [ ] Correr replay específico de pushback.
- [ ] Ajustar prompt para equilibrio entre avance y prudencia.
