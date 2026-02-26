# Runtime Diagnostic Report

## Qué fallaba
1. Planner devolvía `next_move_hint` inline, a veces con `TEMA` inválido (phase id) y `?` dentro de `RESPUESTA`.
2. Executor podía contaminar salida con claves de planner (`phase/style/next_move_hint/response`) y romper `executor_v2`.
3. `PHASE_CARD_EXTENDIDA` no estaba anclada literal al contenido operativo de docs de fase.
4. Coherencia `asked_question` / `requested_info_slots` era débil en casos límite.

## Causa
- Contrato del prompt planner no era suficientemente explícito para formato 3/4 líneas + restricciones de `?`.
- Prompt executor no mostraba el schema literal en primera línea de saliencia y no tenía regla dura anti-contaminación.
- Catálogo de phase cards estaba resumido y no literal al contenido operativo.
- Validaciones runtime no alineaban completamente `?`, `asked_question` y `requested_info_slots`.

## Cambios exactos
- `backend/prompts.py`
  - Planner SYSTEM actualizado con:
    - Formato obligatorio 3 o 4 líneas.
    - `PREGUNTA` opcional.
    - `¿?` solo en `PREGUNTA` y `TEMA`.
    - `TEMA` exacto de `TOPICS_POR_FASE` y prohibición de usar phase id.
    - Excepción de control de fase para saltos 2+ cuando usuario adelanta precio/cierre/logística.
    - límites de longitud por línea.
- `backend/negotiation/phase_policy_planner.py`
  - `_normalize_next_move_hint` ahora:
    - normaliza saltos de línea,
    - mueve `?` desde `RESPUESTA`/`MOVIMIENTO` a `PREGUNTA`,
    - no inventa `PREGUNTA` si no hay pregunta a mover,
    - valida `TEMA` por phase y aplica fallback por phase.
- `backend/negotiation/elementos/render/executor_prompts.py`
  - Schema `executor_v2` literal dentro de SYSTEM.
  - Regla anti-contaminación de claves.
  - Reglas estrictas de coherencia `?`/`asked_question`/`requested_info_slots`.
  - Refuerzo SOLO TEXTO con lista literal de verbos prohibidos.
  - Reordenado USER: `PLANNER_OUTPUT` -> `PHASE_CARD_EXTENDIDA` (una card) -> resto.
- `backend/negotiation/phase_cards_extended.py`
  - Cards extendidas con estructura runtime:
    - `phase_id`, `do_text`, `tecnicas_text`, `evitar_text`, `question_policy`, `topics`.
  - Contenido operativo copiado literal de docs de fase (DO/TÉCNICAS/EVITAR/QUESTION_POLICY + topics exactos).
- `backend/negotiation/executor/render_executor.py`
  - Inyección de una sola card por `planner.phase`.
  - `topic_selected` derivado de `TEMA` + fallback (`phase_default` / `invalid_fallback`).
  - Retry por schema inválido antes de wordcap/text-only.
  - Salvage `response -> response_text`.
  - Enforce coherencia `asked_question` / `requested_info_slots`.

## Snippets de referencia (paths)
- Planner normalize: `backend/negotiation/phase_policy_planner.py` (`_normalize_next_move_hint`).
- Phase cards: `backend/negotiation/phase_cards_extended.py` (`_PHASE_CARDS_EXTENDED`, `get_phase_card_extended`).
- Executor retry/coherencia: `backend/negotiation/executor/render_executor.py` (`_is_valid_executor_v2_payload`, `_salvage_response_text`, `_enforce_executor_v2_contract`, `render_executor_output`).
- Prompt schema anchor: `backend/negotiation/elementos/render/executor_prompts.py`.

## Repro mínimo + smoke real
### Comando
```bash
PYTHONPATH=backend python - <<'PY'
from negotiation.phase_policy_planner import _normalize_next_move_hint
cases = [
    ("hola", "clima_humano", 'RESPUESTA: Hola, encantado de hablar contigo. MOVIMIENTO: Mantener tono cordial y abrir conversación. TEMA: "clima_humano"'),
    ("¿cuánto pides?", "concesiones_y_ajuste_final", 'RESPUESTA: Te respondo directo. MOVIMIENTO: Enmarcar rango y condicionar cierre rápido. PREGUNTA: ¿Cuál sería tu margen real hoy? TEMA: "Precio vs comodidad (fecha/recogida/papeleo)"'),
    ("vale, cerramos hoy, ¿dónde quedamos?", "formalizacion_del_acuerdo", 'RESPUESTA: Perfecto, cerramos hoy. MOVIMIENTO: Confirmo pago, fecha y lugar por texto. PREGUNTA: ¿Te viene bien vernos en punto céntrico? TEMA: "Checklist: entrega y trámites"'),
]
for user, phase, raw in cases:
    hint, changed = _normalize_next_move_hint(phase, raw)
    print('USER_MESSAGE=', user)
    print('PHASE=', phase)
    print('NORMALIZED_CHANGED=', changed)
    print(hint)
    print('---')
PY
```

### Output
```text
USER_MESSAGE= hola
PHASE= clima_humano
NORMALIZED_CHANGED= True
RESPUESTA: Hola, encantado de hablar contigo.
MOVIMIENTO: Mantener tono cordial y abrir conversación.
TEMA: "Pequeño rapport: día / cómo está"
---
USER_MESSAGE= ¿cuánto pides?
PHASE= concesiones_y_ajuste_final
NORMALIZED_CHANGED= True
RESPUESTA: Te respondo directo.
MOVIMIENTO: Enmarcar rango y condicionar cierre rápido.
PREGUNTA: ¿Cuál sería tu margen real hoy?
TEMA: "Precio vs comodidad (fecha/recogida/papeleo)"
---
USER_MESSAGE= vale, cerramos hoy, ¿dónde quedamos?
PHASE= formalizacion_del_acuerdo
NORMALIZED_CHANGED= True
RESPUESTA: Perfecto, cerramos hoy.
MOVIMIENTO: Confirmo pago, fecha y lugar por texto.
PREGUNTA: ¿Te viene bien vernos en punto céntrico?
TEMA: "Checklist: entrega y trámites"
---
```

## Tests ejecutados
```bash
pytest -q backend/tests/test_prompt_swap_wiring.py backend/tests/test_semantic_runtime_v1.py
```
Resultado:
```text
27 passed
```
