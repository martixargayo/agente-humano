# 04 — Loop de precio y repregunta tras pushback del usuario

## Síntoma observado
- En Turno 16 (reporte): usuario dice “prefiero que lo digas tú”.
- Bot responde repitiendo “¿qué precio tienes en mente?”, ignorando el pushback explícito.

## Evidencias de LiveTrace (campos/mismatch)
- En prompts no aparece un flag estructurado de rechazo de slot (`price_pushback` / `counterparty_refused_slot`).
- `semantic_ledger` no contiene un bucket explícito para “slot refusals” o “counter-offer requested”.

## Hipótesis de causa raíz (root cause)
### Causa principal
- Falta modelado de estado para “rehúso de slot precio”.
- Sin esa memoria de control, planner/executor vuelven a la táctica por defecto de preguntar precio.

### Causa secundaria
- El desfase de ledger (problema 01) agrava el loop: el planner puede no ver correctamente lo ya preguntado o la resistencia reciente.

## Pistas concretas en código
- Estructura de ledger actual no contempla pushback/refusal flags.
- `progress_updater` sólo sincroniza tres listas semánticas; no hay señal de “slot refused”.
- Executor tiene regla de no repetición, pero depende de ledger incompleto.

### Snippets relevantes
```python
# backend/negotiation/schemas.py
"lo_que_ya_se_toco": [],
"lo_que_ya_pregunte": [],
"lo_que_falta_pero_no_insistire": [],
```

```python
# backend/negotiation/progress_updater.py
incoming = (semantic_judge or {}).get("semantic_ledger")
for key in semantic_ledger:
    val = incoming.get(key)
    if isinstance(val, list):
        semantic_ledger[key] = [...]
```

## Pruebas/validaciones para demostrarlo
1. **Test de pushback price-slot**:
   - Historial: bot pide precio, user responde “prefiero que lo digas tú”.
   - Assert: siguiente salida no repregunta precio; ofrece rango/primera ancla.
2. **Nueva telemetría de slots**:
   - Registrar `slot_state.price = {requested, refused, offered_by_assistant}` en cada turno.
3. **Contrato de no-loop**:
   - Si `price_refused=true`, bloquear preguntas equivalentes sobre precio durante X turnos.

## Parche sugerido (propuesta, no implementado)
- Extender estado con:
  - `slot_negotiation_state.price.pushback_count`
  - `slot_negotiation_state.price.refused_by_counterparty`
  - `slot_negotiation_state.price.last_assistant_offer`
- Ajustar planner policy:
  - Ante pushback, cambiar a estrategia de anclaje propio (rango u oferta condicional) en vez de re-preguntar.

## Riesgos y casos borde
- Un usuario puede cambiar de idea y luego sí querer dar precio; el bloqueo no debe ser absoluto.
- Debe manejarse lenguaje ambiguo (“depende”, “no sé”) sin forzar falsa detección de rechazo.
