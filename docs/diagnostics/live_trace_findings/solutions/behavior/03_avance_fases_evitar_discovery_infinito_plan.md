# 03 — Avance por fases y evitar discovery infinito

## 1) Síntoma observado
- El sistema puede quedarse en bucle de descubrimiento (preguntas sucesivas) sin mover claramente hacia propuesta/concesión/cierre.
- Falta sensación de progreso hacia objetivo comprador (cerrar compra en condiciones favorables).

## 2) Evidencia (LiveTrace + código)
- El planner produce `phase`, `style`, `next_move_hint`, pero no existe una instrucción explícita de “progreso neto por turno” vinculada al objetivo de cierre.
- `phase_map` detalla fases de avance, pero en discovery el repertorio de preguntas es amplio y puede dominar.
- `objective_summary` puede terminar genérico si no está bien especificado en estado, debilitando intención de negociación real.

### Snippets de evidencia
```python
# backend/prompts.py
PLANNER_SEMANTIC_V1_USER_PROMPT = "... OBJECTIVE_SUMMARY ... SEMANTIC_LEDGER_JSON ... phase/style/next_move_hint ..."
```

```text
# backend/negotiation/phase_map.py
"descubrimiento_y_comprension": {
  "preguntas_recomendadas_mustang": [...]
}
```

```python
# backend/negotiation/llm_planning_context.py
build_objective_summary(...)
```

## 3) Hipótesis de causa raíz
1. Planner optimiza micro-coherencia local (siguiente turno) más que progreso acumulado.
2. Falta instrucción explícita de “si esto no acerca al cierre, cambia de táctica”.
3. Perfil comprador prudente + no agresivo puede derivar a exceso de cautela interrogativa.

## 4) Dónde mirar en el repo (rutas confirmadas)
- `backend/negotiation/phase_policy_planner.py`
- `backend/prompts.py` (`PLANNER_SEMANTIC_V1_*`)
- `backend/negotiation/phase_map.py`
- `backend/negotiation/llm_planning_context.py` (`build_objective_summary`)
- `backend/negotiation/elementos/render/carlos_buyer_preset.py`

## 5) Cambios propuestos SOLO en prompting/contexto (texto exacto)

### 5.1 Planner prompt: prioridad de progreso
Añadir bloque:

```text
PROGRESO_NEGOCIADOR:
- Evalúa si tu next_move_hint acerca al objetivo principal (comprar bien y cerrar en condiciones favorables).
- Si el turno no añade progreso real (solo más exploración repetida), propone pivot a propuesta/concesión/ajuste.
- Evita discovery infinito: cuando ya haya contexto suficiente, prioriza mover fase.
```

### 5.2 Planner prompt: brújula de objetivo
Añadir bloque:

```text
BUYER_INTENT:
- El comprador busca pagar lo mínimo razonable sin romper la conversación.
- Tus hints deben equilibrar cordialidad con intención negociadora real.
```

### 5.3 Executor prompt: traducción a acción conversacional
Añadir bloque:

```text
[PROGRESO_POR_TURNO]
- Si ya hay contexto suficiente, evita volver a preguntas exploratorias.
- Prioriza movimientos que acerquen acuerdo: anclar, comparar escenarios, proponer siguiente paso de cierre.
```

## 6) Ejemplos antes/después
- **Antes:** “¿Cómo lo has cuidado? ¿y antes? ¿y revisiones?”
- **Después:** “Con lo que ya me comentaste, tengo base suficiente. Si te encaja, pasemos a una propuesta concreta de cierre.”

- **Antes:** discovery extendido sin propuesta.
- **Después:** “Entendido. Te propongo una referencia inicial y vemos cómo ajustarla para cerrar bien los dos.”

## 7) Plan de pruebas (replay) + métricas semánticas
- Replay de conversaciones de 15–20 turnos.
- LLM-judge:
  - ¿Hubo avance real de fase o estancamiento?
  - ¿Se percibe intención de cierre razonable?
- Métricas:
  - `phase_progression_score`
  - `stalled_discovery_turns`
  - `toward_close_intent_score`

## 8) Riesgos y mitigación
- Riesgo: acelerar demasiado hacia cierre sin suficiente confianza.
- Mitigación: prompt “mover fase cuando haya contexto suficiente”, no “cerrar siempre rápido”.
- Riesgo: sonar más duro/agresivo.
- Mitigación: mantener tono respetuoso y colaborativo en wording.

## 9) Notas LLM-first
- Plan basado en objetivos conversacionales y calidad de dirección estratégica del prompt.
- Sin automatismos rígidos de transición de fase.
