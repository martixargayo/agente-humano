# Documento 2 — Mapa funcional: cambios necesarios en runtime

## Objetivo operativo
Adaptar runtime al nuevo contrato de prompts sin rutas legacy activas.

## 1) Retirar dependencias legacy de `NECESITA_INFO`

### 1.1 Planner runtime
1. Retirar parsing de `NECESITA_INFO` en normalización de `next_move_hint`.
2. Retirar postcheck que detecta intención de pedir información para forzar `NECESITA_INFO`.
3. Retirar retry por ausencia de `NECESITA_INFO`.
4. Retirar mapeos topic→slot usados para forzar slots.
5. Retirar metadato funcional `planner_need_info_slots`.

### 1.2 Executor runtime
1. Retirar construcción y paso de `need_info_slots` al prompt del executor.
2. Retirar extracción de slots desde `next_move_hint` para permitir pregunta.
3. Retirar gating de preguntas basado en `bool(need_info_slots)`.
4. Mantener `asked_question` y `requested_info_slots` como parte del schema `executor_v2`, pero desacoplados del planner.

## 2) Parsing de `next_move_hint` por marcador (nuevo contrato)

## Campos obligatorios a parsear
1. `OBJECTIVE_DELTA:`
2. `TACTIC:`
3. `RESPUESTA:`
4. `MOVIMIENTO:`
5. `TEMA:`

## Reglas de parseo
1. Parsear por marcador nominal, no por posición de línea.
2. Conservar `TEMA` como label exacto válido para la fase.
3. Si falta marcador:
   - `objective_delta = reduce_risk`
   - `tactic = frame`
4. Mantener fallback de topic por fase cuando `TEMA` no sea válido.

## 3) Ajustes de telemetría y metadata

## 3.1 Señales a desactivar como funcionales
1. `planner_need_info_slots` (dejar de usar para decisiones).
2. Señales derivadas de forced slots/retry por NECESITA_INFO.

## 3.2 Señales nuevas/derivadas a exponer
1. `objective_delta` parseado.
2. `tactic` parseado.
3. `hint_contract_ok` (marcadores presentes).
4. `question_policy_source` (executor autónomo).

## 4) Coherencia de schema `executor_v2`
1. `asked_question` permanece obligatorio en salida.
2. `requested_info_slots` permanece obligatorio en salida.
3. `requested_info_slots` ya no depende de planner slots.
4. Política objetivo:
   - si `asked_question=false` ⇒ `requested_info_slots=[]`
   - si `asked_question=true` ⇒ `requested_info_slots` inferido por executor/finalizer.

## 5) Summarizer v2: validaciones funcionales
1. Verificar presencia estable de secciones:
   - `BOUNDARIES_Y_COMPROMISOS`
   - `BANDERAS_DEL_VENDEDOR`
   - `LECCIONES_DE_CONDUCTA`
2. Verificar cumplimiento de privacidad:
   - no persistir cifras sensibles del comprador
   - usar abstracciones de límite privado
3. Verificar compatibilidad de consumo:
   - `memory_long_compact` disponible para planner/executor/finalizer.

## 6) Dependencias por archivo a intervenir
1. `backend/negotiation/phase_policy_planner.py`
2. `backend/negotiation/nodes/planner_node.py`
3. `backend/negotiation/executor/render_executor.py`
4. `backend/negotiation/phase_cards_extended.py` (solo compatibilidad de extracción de `TEMA`)
5. `backend/prompts.py`
6. `backend/negotiation/elementos/render/executor_prompts.py`

## 7) Secuencia de implementación
1. Cambiar contrato de prompts activos.
2. Limpiar lógica `NECESITA_INFO` en planner.
3. Limpiar wiring/gating `need_info_slots` en executor.
4. Activar parsing por marcadores nuevos.
5. Ajustar telemetría y metadatos.
6. Validación manual de turnos cortos/largos.
