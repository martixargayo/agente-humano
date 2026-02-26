# 01 — Anti-interrogatorio y reducción de preguntas (prompt-first)

## 1) Síntoma observado
- En LiveTrace se observa patrón recurrente “responder + preguntar” en casi todos los turnos.
- El diálogo deriva a ritmo de interrogatorio, incluso cuando bastaría validar y cerrar turno.

## 2) Evidencia (LiveTrace + código)
- El preset de persona incluye explícitamente: `asks one focused question per turn`, lo que empuja al modelo hacia pregunta sistemática.
- El contrato de estilo limita a `max_questions=1`, pero no incentiva `0`; en práctica funciona como “haz 1 si puedes”.
- El prompt de executor permite 0 preguntas, pero no define una política de frecuencia/ritmo (cuándo conviene callar y ceder).
- En fase de descubrimiento el `phase_map` enfatiza preguntar, con listas de preguntas recomendadas.

### Snippets de evidencia
```python
# backend/negotiation/elementos/render/carlos_buyer_preset.py
"trait_markers": [
    "asks one focused question per turn about reliability, history, or paperwork",
]
```

```text
# backend/negotiation/elementos/render/executor_prompts.py
- No estás obligado a cerrar con pregunta en todos los turnos.
- Si decides preguntar, haz como máximo 1 pregunta total.
```

```python
# backend/negotiation/elementos/render/carlos_buyer_preset.py
CARLOS_STYLE_CONTRACT = {"max_questions": 1, ...}
```

## 3) Hipótesis de causa raíz
1. **Sesgo de persona**: rasgo explícito “one question per turn” en perfil Carlos.
2. **Sesgo de fase**: `descubrimiento_y_comprension` está descrita con foco en pregunta, sin un presupuesto de preguntas por bloque de turnos.
3. **Sesgo de schema**: salida del executor obliga a declarar `asked_question`; aunque permite `false`, el entrenamiento de instrucción queda ambiguo en frecuencia.
4. **Falta de objetivo rítmico explícito**: no existe instrucción tipo “en bastantes turnos, responde y termina”.

## 4) Dónde mirar en el repo (rutas confirmadas)
- `backend/negotiation/elementos/render/carlos_buyer_preset.py`
- `backend/negotiation/elementos/render/style_contracts.py`
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/negotiation/phase_map.py`
- `backend/negotiation/executor/render_executor.py`

## 5) Cambios propuestos SOLO en prompting/contexto (texto exacto)

### 5.1 Executor prompt (`EXECUTOR_V2_SYSTEM_PROMPT`)
Añadir bloque:

```text
[RITMO_ANTI_INTERROGATORIO — PRIORIDAD]
- Tu objetivo NO es preguntar en cada turno.
- En una proporción significativa de turnos, responde y cierra sin pregunta.
- Si el usuario acaba de dar información útil, prioriza validar + avanzar sin interrogatorio.
- Haz pregunta solo cuando desbloquee una decisión real; si no, cede iniciativa.
```

### 5.2 Planner prompt (`PLANNER_SEMANTIC_V1_USER_PROMPT`)
Añadir bloque:

```text
RHYTHM_GUIDE:
- Diseña next_move_hint con cadencia humana: alterna turnos de pregunta con turnos de validación/cierre.
- Evita secuencias largas de preguntas consecutivas si la conversación ya progresa.
- Es válido y recomendable proponer "respuesta sin pregunta" cuando ayude al rapport o claridad.
```

### 5.3 Contexto auxiliar suave (sin rail duro)
- Inyectar en prompt (si disponible) una métrica observacional de contexto: `recent_question_density` (solo informativa, no bloqueante).
- Uso esperado por LLM: bajar iniciativa cuando densidad reciente de preguntas ya es alta.

## 6) Ejemplos antes/después
- **Antes:** “Entiendo. ¿Y qué mantenimiento tuvo? ¿Y la ITV? ¿Y propietarios?”
- **Después:** “Perfecto, me queda claro lo del mantenimiento y la ITV. Si te parece, seguimos cuando quieras con el siguiente punto.”

- **Antes:** “Gracias por explicarlo. ¿Algo más? ¿Qué cifra? ¿Tienes prisa?”
- **Después:** “Gracias, con eso ya tengo buena base. Te escucho: ¿cómo prefieres avanzar?”

## 7) Plan de pruebas (replay) + métricas semánticas
- Replay en sesiones largas con múltiples turnos informativos del vendedor.
- LLM-judge (semántico):
  - ¿El asistente evita tono de interrogatorio?
  - ¿Cede iniciativa de forma natural?
- Métricas:
  - `question_turn_rate` (objetivo: bajar, no a cero)
  - `consecutive_question_streak_p95`
  - `interrogation_feel_score` (LLM-judge)

## 8) Riesgos y mitigación (sin rails duros)
- Riesgo: pasividad excesiva.
- Mitigación: instrucción explícita “preguntar cuando desbloquea decisión real”.
- Riesgo: pérdida de información relevante.
- Mitigación: mantener preguntas enfocadas en momentos clave, no como hábito.

## 9) Notas LLM-first
- Este plan no usa regex ni validadores bloqueantes.
- Se basa en prioridades de ritmo conversacional y contexto semántico.
