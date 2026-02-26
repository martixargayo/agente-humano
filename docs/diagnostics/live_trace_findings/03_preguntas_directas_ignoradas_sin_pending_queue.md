# 03 — Se ignoran preguntas directas del usuario (falta de `pending_counterparty_questions`)

## Síntoma observado
- En Turno 14 (según reporte), el usuario pregunta explícitamente:
  - por qué interesa el coche
  - qué está dispuesto a ofrecer
- La respuesta del bot no atiende esas preguntas y vuelve a pedir precio.

## Evidencias de LiveTrace (campos/mismatch)
- Prompt de executor incluye la regla `[COMMON_SENSE_HUMAN_FIRST]` (“NUNCA ignores una pregunta directa…”).
- Aun así, salida final no responde lo preguntado.
- Planner/executor no parecen recibir un campo estructurado de “preguntas pendientes del interlocutor” para forzar prioridad de respuesta.

## Hipótesis de causa raíz (root cause)
### Causa principal (modelo de estado incompleto)
- El ledger actual sólo modela:
  - `lo_que_ya_se_toco`
  - `lo_que_ya_pregunte`
  - `lo_que_falta_pero_no_insistire`
- No existe una estructura explícita tipo `pending_counterparty_questions`.
- Sin esta estructura, el planner optimiza por `next_move_hint` y puede priorizar negociación/precio sobre respuesta directa.

### Causa secundaria (enforcement insuficiente en executor)
- La regla está en prompt, pero no hay validador determinista previo/post que bloquee salidas que omiten una pregunta detectada en el último turno del usuario.

## Pistas concretas en código
- Esquema default de ledger sin bucket para preguntas del contraparte.
- Prompt executor sí contiene regla human-first, pero la salida depende completamente del LLM.
- No se detecta extractor determinista de pregunta directa ni guardado en estado.

### Snippets relevantes
```python
# backend/negotiation/schemas.py
def default_semantic_ledger() -> Dict[str, List[str]]:
    return {
        "lo_que_ya_se_toco": [],
        "lo_que_ya_pregunte": [],
        "lo_que_falta_pero_no_insistire": [],
    }
```

```text
# backend/negotiation/elementos/render/executor_prompts.py
[COMMON_SENSE_HUMAN_FIRST — REGLA CRÍTICA]
- NUNCA ignores una pregunta directa del usuario.
- Responde primero a lo que el usuario acaba de decir/preguntar...
```

## Pruebas/validaciones para demostrarlo
1. **Test de compliance conversacional**:
   - Input user con pregunta directa compuesta.
   - Assert sobre salida: contiene respuesta semántica a esa pregunta antes de nueva pregunta.
2. **Instrumentación de detector**:
   - Antes del executor, detectar preguntas en `user_message` (heurística + regex + llm classifier opcional).
   - Loggear `detected_counterparty_questions` y `answered_counterparty_questions`.
3. **Guardrail assertivo**:
   - Si hay pregunta detectada y salida no la aborda, marcar `executor_contract_violation` en trace.

## Parche sugerido (propuesta, no implementado)
- Añadir estado:
  - `pending_counterparty_questions: list[str]`
  - `answered_counterparty_questions: list[str]` (opcional)
- Poblar en world/judge (o extractor determinista dedicado).
- Regla de planner: si hay pendientes, `next_move_hint` debe priorizar responder una.
- Validator post-executor: rechazar/reintentar respuesta si omite pendiente crítica.

## Riesgos y casos borde
- Detección de preguntas implícitas puede producir falsos positivos.
- Si hay múltiples preguntas en un turno, conviene priorizar 1 y reconocer las demás (“te respondo por partes…”).
- Debe evitarse respuestas robóticas por sobreaplicación de guardrail.
