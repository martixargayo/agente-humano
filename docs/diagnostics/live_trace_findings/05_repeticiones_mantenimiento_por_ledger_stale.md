# 05 — Repeticiones (mantenimiento) por ledger desactualizado y anti-repetición parcial

## Síntoma observado
- Se repite la pregunta de mantenimiento en turnos posteriores pese a haber sido respondida antes.
- Ejemplo reportado: secuencia 8→10→12→14 con reproche del vendedor (“ya te lo comenté…”).

## Evidencias de LiveTrace (campos/mismatch)
- En turnos con repetición, planner recibe `SEMANTIC_LEDGER_JSON` vacío/desactualizado mientras judge/executor ven datos más recientes.
- El prompt del executor sí incluye reglas anti-repetición basadas en ledger, pero llega tarde para corregir un `next_move_hint` ya sesgado por planner.

## Hipótesis de causa raíz (root cause)
### Causa principal
- Misma desincronización del problema 01: planner decide con ledger viejo.
- El mecanismo anti-repetición está acoplado al planner pero su input de memoria táctica no está actualizado en ese punto del pipeline.

### Causa secundaria
- Ledger modela “preguntado”/“tratado”, pero no hay verificación determinista final de duplicación semántica antes de emitir pregunta.

## Pistas concretas en código
- Planner usa `semantic_ledger_json` desde `progress_state`.
- Merge judge→progress sucede después del planner.
- Executor prompt contiene cláusulas explícitas de no repetir (`lo_que_ya_pregunte`), pero depende de que esa lista esté bien poblada y a tiempo.

### Snippets relevantes
```text
# backend/prompts.py (planner)
SEMANTIC_LEDGER_JSON: {semantic_ledger_json}
```

```python
# backend/negotiation/phase_policy_planner.py
semantic_ledger = (progress_state or {}).get("semantic_ledger", {})
```

```text
# backend/negotiation/elementos/render/executor_prompts.py
- Si algo ya aparece en lo_que_ya_pregunte: NO repitas esa pregunta ni la reformules.
```

## Pruebas/validaciones para demostrarlo
1. **Replay test multi-turno (8→14)**:
   - Simular respuestas del vendedor donde mantenimiento ya está contestado.
   - Assert: ni planner `next_move_hint` ni executor `response_text` vuelven a pedir mantenimiento.
2. **Similarity guard**:
   - Antes de emitir pregunta, comparar contra últimas preguntas del asistente (embedding o heurística léxica).
   - Si similitud alta, bloquear/reformular.
3. **Trace diff**:
   - Exponer en LiveTrace2: `planner_seen_ledger` vs `executor_seen_ledger` para detectar drift automáticamente.

## Parche sugerido (propuesta, no implementado)
- Aplicar fix de sincronización (problema 01) como prerequisito.
- Añadir guardrail determinista anti-duplicación en executor/post-processor.
- Considerar expandir ledger con canonicalización de intents de pregunta (no solo texto literal).

## Riesgos y casos borde
- Preguntas parecidas pero legítimamente distintas podrían bloquearse por heurísticas agresivas.
- Requiere balance entre evitar repetición y mantener descubrimiento cuando la respuesta previa fue vaga.
