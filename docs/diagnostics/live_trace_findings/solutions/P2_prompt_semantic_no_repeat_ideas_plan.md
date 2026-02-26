# P2 — Prompt Semantic: no repetir IDEAS (aunque cambie el wording)

## 1) Síntoma + referencia LiveTrace
- Repeticiones de mantenimiento con formulaciones distintas (misma idea general ya tratada).
- Referencia base: `../05_repeticiones_mantenimiento_por_ledger_stale.md`.

## 2) Objetivo / Definition of Done
**Objetivo:** evitar repetición por IDEA conversacional, manteniendo libertad lingüística.

**DoD**
- Reducción clara de `idea_repeat_rate` en replay.
- Sin caída relevante en naturalidad/variación del lenguaje.
- Sin taxonomía rígida ni dedup por thresholds duros como control principal.

## 3) Propuesta (centrada en prompt changes)

### 3.1 Planner: anti-repetición por idea
**Ruta:** `backend/prompts.py` (`PLANNER_SEMANTIC_V1_USER_PROMPT`).

**Texto exacto sugerido**

```text
IDEA_LEVEL_NO_REPEAT:
- Evalúa repetición por IDEA GENERAL, no por coincidencia literal.
- Si una idea ya fue tratada o preguntada (según SEMANTIC_LEDGER_JSON y MEMORY_LONG),
  no la reabras con otra redacción equivalente salvo que exista información nueva relevante.
- Prioriza next_move_hint que aporte novedad real.
```

### 3.2 Executor: usar ledger + memory_long como ancla de novedad
**Ruta:** `backend/negotiation/elementos/render/executor_prompts.py` (`EXECUTOR_V2_SYSTEM_PROMPT`).

**Texto exacto sugerido**

```text
[NO-REPEAT BY IDEA]
- Evita repetir la misma idea central aunque cambien las palabras.
- Usa SEMANTIC_LEDGER_JSON y MEMORY_LONG para decidir si ya está cubierto.
- Si ya está cubierto, valida brevemente y avanza con una idea nueva o un cierre útil.
```

### 3.3 Summarizer: memoria accionable para no repetir
**Ruta:** `backend/prompts.py` (`SUMMARY_USER_PROMPT`).

**Texto exacto sugerido**

```text
NOVEDAD_Y_REPETICION:
- Marca en el resumen qué ideas ya quedaron suficientemente tratadas.
- Señala qué temas no conviene volver a preguntar salvo nueva información.
```

## 4) Ejemplos antes/después
### Ejemplo 1 (mantenimiento)
- Antes: “¿Cómo lo has mantenido estos años?”
- Después (si ya respondió): “Perfecto, mantenimiento claro. Para avanzar, ¿cómo ves el cierre en tiempos?”

### Ejemplo 2 (estado general)
- Antes: “¿Qué tal está de estado?” → luego “¿Cómo está en general?”
- Después: “Gracias, el estado me queda claro. Paso al siguiente punto para decidir.”

### Ejemplo 3 (precio)
- Antes: “¿Qué precio tienes?” → “¿En qué cifra lo valoras?”
- Después: “Entendido, para no repetir lo mismo, te comparto mi referencia y vemos si nos acercamos.”

## 5) Plan de pruebas (replay) y métricas
- Replay con paraphrasing de una misma idea en distintos turnos.
- LLM-judge semántico:
  - ¿Aporta novedad real?
  - ¿Evita repetir la misma idea?
- Métricas:
  - `idea_repeat_rate`
  - `novelty_score`
  - `coherence_score`

## 6) Riesgos y tradeoffs
- Riesgo: “evitar repetición” interpretado en exceso y perder aclaraciones útiles.
- Mitigación: permitir reabrir tema cuando el usuario lo pida o haya dato nuevo.
- Tradeoff: mejor fluidez y menos loops, con ligera menor insistencia exploratoria.

## 7) Checklist implementación futura
- [ ] Añadir bloque `IDEA_LEVEL_NO_REPEAT` al planner prompt.
- [ ] Añadir bloque `NO-REPEAT BY IDEA` al executor prompt.
- [ ] Añadir sección de novedad/repetición al summary prompt.
- [ ] Ejecutar replay de paraphrasing y validar métricas semánticas.
