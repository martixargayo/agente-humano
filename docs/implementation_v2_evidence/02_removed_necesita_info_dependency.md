# 02 — Dependencia eliminada de `NECESITA_INFO` / `need_info_slots`

## Claim
`NECESITA_INFO` y `need_info_slots` ya no forman parte funcional del runtime planner/executor.

## Evidence
- En planner, la normalización elimina explícitamente cualquier línea `PREGUNTA:` y reconstituye `next_move_hint` con 5 marcadores (`OBJECTIVE_DELTA`, `TACTIC`, `RESPUESTA`, `MOVIMIENTO`, `TEMA`):
  - `backend/negotiation/phase_policy_planner.py` líneas 87–92 y 118–124.
- En planner, metadata funcional se centra en `planner_objective_delta`, `planner_tactic`, `planner_hint_contract_ok`:
  - `backend/negotiation/phase_policy_planner.py` líneas 245–256.
- En executor no se recibe ni usa `need_info_slots` en el prompt de usuario activo:
  - `backend/negotiation/elementos/render/executor_prompts.py` líneas 99–157 (no existe campo `need_info_slots`).
- En render del executor se fuerza `question_allowed = True` (sin gating por slots de planner):
  - `backend/negotiation/executor/render_executor.py` líneas 391 y 474.
- Búsqueda de runtime sin hallazgos:
  - `rg -n "NECESITA_INFO|need_info_slots|planner_need_info_slots" backend/negotiation backend/prompts.py --glob '!backend/tests/**'`
  - salida: sin coincidencias.

## Reasoning
No existen referencias runtime a los campos legacy ni mecanismos de retry/gating asociados. El contrato activo quedó migrado al parseo por marcadores y a metadatos `objective_delta/tactic`.

## How to reproduce
1. Inspeccionar planner:
   - `nl -ba backend/negotiation/phase_policy_planner.py | sed -n '66,140p'`
   - `nl -ba backend/negotiation/phase_policy_planner.py | sed -n '240,270p'`
2. Inspeccionar prompt executor y render:
   - `nl -ba backend/negotiation/elementos/render/executor_prompts.py | sed -n '99,180p'`
   - `nl -ba backend/negotiation/executor/render_executor.py | sed -n '360,500p'`
3. Verificar ausencia global en runtime:
   - `rg -n "NECESITA_INFO|need_info_slots|planner_need_info_slots" backend/negotiation backend/prompts.py --glob '!backend/tests/**'`
