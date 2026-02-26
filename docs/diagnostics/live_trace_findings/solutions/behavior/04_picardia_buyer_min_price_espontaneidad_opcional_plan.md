# 04 — Picardía negociadora (buyer quiere mínimo precio) + espontaneidad opcional

## 1) Síntoma observado
- El asistente suena demasiado correcto/neutral y poco negociador.
- Falta “picardía” (presión suave, anclaje prudente, dudas razonables, movimientos tácticos no agresivos).

## 2) Evidencia (LiveTrace + código)
- Persona actual enfatiza prudencia/fairness/safety; protege de agresión, pero no explicita suficiente “ambición negociadora”.
- En `hard_limits` y `forbid_behaviors` hay (correctamente) límites de no agresión, pero falta instrucción positiva de “negociar de verdad para minimizar precio”.
- El prompt de executor prioriza coherencia/human-first/no repetición, pero no explicita repertorio de “moves” negociadores suaves.

### Snippets de evidencia
```python
# backend/negotiation/elementos/render/carlos_buyer_preset.py
"values": ["prudence", "fairness", "safety", "clarity"]
"hard_limits": ["will not threaten or pressure; keeps tone respectful", ...]
```

```text
# backend/negotiation/elementos/render/executor_prompts.py
- Sin amenazas ni presión agresiva.
- No revelar BATNA/presupuesto máximo.
```

```python
# backend/negotiation/elementos/render/carlos_buyer_preset.py
"goals": ["buy the car at a reasonable price with low risk", ...]
```

## 3) Hipótesis de causa raíz
1. Seguridad/cordialidad bien definidas; intención de compra al mínimo precio definida de forma débil.
2. Planner/executor no tienen guía explícita de “micro-movimientos negociadores” alternativos a preguntar.
3. Falta mecanismo suave de variación de estilo táctico (espontaneidad controlada) para evitar monotonía.

## 4) Dónde mirar en el repo (rutas confirmadas)
- `backend/negotiation/elementos/render/carlos_buyer_preset.py`
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/prompts.py` (`PLANNER_SEMANTIC_V1_USER_PROMPT`)
- `backend/negotiation/phase_map.py`

## 5) Cambios propuestos SOLO en prompting/contexto (texto exacto)

### 5.1 Planner prompt: intención negociadora explícita
Añadir bloque:

```text
NEGOTIATION_EDGE:
- Mantén tono respetuoso, pero con intención clara de compra al precio más bajo razonable.
- Favorece next_move_hint con valor táctico: ancla prudente, comparación de escenarios, concesión condicionada, cierre con contrapartida.
- Evita neutralidad plana: cada turno debe aportar avance negociador o posicionamiento útil.
```

### 5.2 Executor prompt: repertorio suave de "moves"
Añadir bloque:

```text
[PICARDIA_RESPETUOSA]
- Puedes usar movimientos negociadores suaves sin ser agresivo:
  - ancla prudente,
  - duda razonable sobre riesgo/coste futuro,
  - concesión pequeña a cambio de cierre,
  - propuesta de cierre rápido con ajuste.
- Sé natural y flexible; no uses plantilla fija.
```

### 5.3 Espontaneidad opcional (NO aplicada aún)
Idea opcional de diseño de prompt:
- Inyectar `micro_style_hint` (texto corto, no determinista) elegido entre 3–4 rasgos: `cauto`, `astuto_suave`, `cierre_practico`, `empatía_firme`.
- Uso: orientar tono del turno, sin cambiar reglas ni imponer gates.

Ejemplo de bloque opcional:

```text
MICRO_STYLE_HINT (opcional): {micro_style_hint}
Interpretación:
- úsalo como matiz de tono, no como obligación rígida.
- prioriza coherencia con user_message y phase.
```

## 6) Ejemplos antes/después (2–3)
### Ejemplo 1
- **Antes:** “Entiendo, gracias por contarme.”
- **Después:** “Entiendo, y justo por ese riesgo de imprevistos yo tendría que moverme en una cifra más prudente.”

### Ejemplo 2
- **Antes:** “Vale, lo pensaré.”
- **Después:** “Si lo dejamos en un rango razonable hoy, por mi parte puedo cerrar sin alargarlo más.”

### Ejemplo 3
- **Antes:** “Perfecto, gracias por la info.”
- **Después:** “Gracias, me encaja el enfoque. Si ajustamos un poco la cifra para cubrir margen de puesta al día, lo veo cerrable.”

## 7) Plan de pruebas (replay) + métricas semánticas
- Replay con escenarios de tensión baja/media y distintos puntos de precio.
- LLM-judge:
  - ¿Se percibe intención negociadora real?
  - ¿Mantiene respeto/no agresión?
  - ¿Evita neutralidad plana repetitiva?
- Métricas:
  - `negotiation_edge_score`
  - `respectfulness_score`
  - `deal_progress_score`

## 8) Riesgos y mitigación
- Riesgo: “picardía” se vuelva agresividad.
- Mitigación: prompt mantiene límites de respeto y no presión hostil.
- Riesgo: variación estilística incoherente.
- Mitigación: `micro_style_hint` opcional y subordinado a contexto/phase.

## 9) Notas LLM-first
- Plan 100% prompting/contexto; no usa heurísticas rígidas.
- La espontaneidad propuesta es opcional, suave y semántica.
