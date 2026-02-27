# 03 — Contrato de parseo por marcador (`next_move_hint`)

## Claim
El contrato activo parsea `next_move_hint` por marcador de línea (no por posición), con fallback a `reduce_risk` y `frame`, y expone esos valores en metadata.

## Evidence
- Parser por marcador en planner:
  - `_extract_line_value(...)` usa regex por etiqueta en `backend/negotiation/phase_policy_planner.py` líneas 46–49.
  - `_normalize_next_move_hint(...)` extrae y valida `OBJECTIVE_DELTA`/`TACTIC` por nombre en líneas 96–107.
  - Rebuild final obligatorio de 5 líneas con etiquetas en líneas 118–124.
- Fallback explícito en planner:
  - Si `OBJECTIVE_DELTA` inválido → `reduce_risk` en línea 103.
  - Si `TACTIC` inválido → `frame` en línea 106.
- Parseo y fallback explícito también en executor path:
  - `_extract_objective_delta_and_tactic` en `backend/negotiation/executor/render_executor.py` líneas 185–193.
  - Uso posterior en render meta (`objective_delta`, `tactic`) en líneas 378–379.
- Metadata operacional en planner node:
  - `planner_objective_delta` / `planner_tactic` en `backend/negotiation/phase_policy_planner.py` líneas 251–252.
  - Propagación a estado en `backend/negotiation/nodes/planner_node.py` líneas 134–135.

## Reasoning
Las rutas críticas del planner y del executor obtienen los valores por etiqueta textual y aplican defaults en caso de ausencia/invalidación. Eso elimina dependencia de orden posicional y mantiene contrato estable para runtime y observabilidad.

## How to reproduce
1. Inspeccionar planner:
   - `nl -ba backend/negotiation/phase_policy_planner.py | sed -n '40,130p'`
   - `nl -ba backend/negotiation/phase_policy_planner.py | sed -n '240,260p'`
2. Inspeccionar executor parse/meta:
   - `nl -ba backend/negotiation/executor/render_executor.py | sed -n '170,210p'`
   - `nl -ba backend/negotiation/executor/render_executor.py | sed -n '360,410p'`
3. Inspeccionar propagación de state:
   - `nl -ba backend/negotiation/nodes/planner_node.py | sed -n '120,150p'`
