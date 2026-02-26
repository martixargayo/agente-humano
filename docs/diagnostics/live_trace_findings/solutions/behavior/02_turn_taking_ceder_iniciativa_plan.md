# 02 — Turn-taking y ceder iniciativa (responder y ya)

## 1) Síntoma observado
- El asistente domina el turno con iniciativa alta casi constante.
- Faltan turnos de “respuesta breve + cierre” que dejen al usuario marcar ritmo/tema.

## 2) Evidencia (LiveTrace + código)
- `phase_map` sugiere “aquí sí se pregunta” en descubrimiento y trae listas de preguntas; esto eleva iniciativa por defecto.
- El executor prioriza `planner_semantic_output_json + semantic_ledger_json`; si planner sugiere movimiento interrogativo, executor lo sigue.
- No existe un principio explícito de “yield turn” como comportamiento deseable frecuente.

### Snippets de evidencia
```text
# backend/negotiation/phase_map.py (descubrimiento_y_comprension)
"Aquí sí se pregunta, pero con iniciativa baja y flexible."
"preguntas_recomendadas_mustang": [...]
```

```text
# backend/negotiation/elementos/render/executor_prompts.py
Instrucciones de prioridad:
- Prioriza: user_message + last_counterparty_utterance + planner_semantic_output_json + semantic_ledger_json.
```

```python
# backend/negotiation/executor/render_executor.py
planner_semantic_output = state.get("planner_semantic_output")
```

## 3) Hipótesis de causa raíz
1. Planner tiende a pensar “avanzar = preguntar”, especialmente en discovery.
2. Executor tiene libertad para 0 preguntas, pero carece de una prioridad de cesión de iniciativa.
3. Persona/estilo compactos pueden comprimir respuestas hacia fórmula corta con pregunta final para “mover” conversación.

## 4) Dónde mirar en el repo (rutas confirmadas)
- `backend/negotiation/phase_map.py`
- `backend/negotiation/phase_policy_planner.py`
- `backend/prompts.py` (`PLANNER_SEMANTIC_V1_USER_PROMPT`)
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/negotiation/executor/render_executor.py`

## 5) Cambios propuestos SOLO en prompting/contexto (texto exacto)

### 5.1 Planner prompt
Añadir bloque:

```text
TURN_TAKING_PRIORITY:
- En muchos turnos, el mejor siguiente movimiento es "responder y ceder".
- Si el usuario acaba de compartir contexto valioso, prioriza validación breve + cierre del turno.
- Usa pregunta solo cuando sea necesaria para desbloquear una decisión o resolver incertidumbre crítica.
```

### 5.2 Executor prompt
Añadir bloque:

```text
[CEDER_INICIATIVA — PRIORIDAD HUMANA]
- No monopolices la conversación con preguntas.
- Son deseables turnos de: validar + responder + cerrar (sin pregunta).
- Deja espacio para que el usuario lleve el ritmo cuando ya aportó contenido útil.
```

### 5.3 Ajuste suave de fase (sin reglas duras)
- En `PHASE_MAP_JSON`, reforzar en discovery:
  - “modo responder-y-ceder” como opción de alta calidad cuando el vendedor se extiende o abre tema.

## 6) Ejemplos antes/después
- **Antes:** “Entiendo, ¿y cómo fue el último año? ¿y gastos? ¿y uso?”
- **Después:** “Perfecto, con eso ya entiendo bien tu contexto. Cuando quieras, seguimos por el punto que te parezca más importante.”

- **Antes:** “Vale, ¿precio? ¿plazo? ¿documentación?”
- **Después:** “Me encaja lo que dices. Te escucho, ¿qué te parece más prioritario cerrar ahora?”

## 7) Plan de pruebas (replay) + métricas semánticas
- Replay con escenarios donde el usuario habla largo y aporta detalles.
- LLM-judge:
  - ¿El asistente cede iniciativa de forma natural?
  - ¿El turn-taking se percibe equilibrado?
- Métricas:
  - `yield_turn_rate`
  - `assistant_initiative_balance_score`
  - `user_lead_turn_ratio`

## 8) Riesgos y mitigación
- Riesgo: el asistente cede demasiado y no negocia.
- Mitigación: prompt mantiene “preguntar cuando desbloquea decisión”.
- Riesgo: pérdida de momentum.
- Mitigación: usar cierres que inviten progreso sin interrogatorio.

## 9) Notas LLM-first
- Enfoque totalmente de prioridades conversacionales y ritmo.
- Sin gates rígidos ni enforcement por patrones literales.
