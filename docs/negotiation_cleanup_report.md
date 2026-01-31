# Negotiation cleanup report

## Metodología (mapa de uso)

1. **Búsqueda de referencias** con `rg` en todo el repo.
   - `plan_policy` y `update_phase_state` aparecen únicamente en tests, no en el grafo principal.
2. **Verificación del grafo activo**: `negotiation_graph.py` sólo usa `phase_policy_planner` + `postprocess_phase_candidate`.
3. **Revisión de dependencias internas** para confirmar que el código legado no afecta al pipeline actual.

## Lista de candidatos

### SAFE TO DELETE (confirmado como legacy)
- **Funciones LLM legacy en negotiation/phase_state_updater.py**
  - **Por qué parece muerto**: `update_phase_state` no es invocado por el grafo actual.
  - **Reemplazo**: `phase_policy_planner` + `postprocess_phase_candidate`.
  - **Riesgo**: bajo (solo tests lo referenciaban).

- **Planner legacy en negotiation/policy_planner.py**
  - **Por qué parece muerto**: `plan_policy` no se invoca desde el grafo actual.
  - **Reemplazo**: `phase_policy_planner.plan_phase_policy`.
  - **Riesgo**: bajo (solo tests lo referenciaban).

### NEEDS REVIEW (posibles candidatos, no eliminados)
- **backend/negotiation/phase_docs/**
  - **Por qué parece muerto**: no hay referencias a estos archivos desde código.
  - **Riesgo**: podría ser documentación de producto, no se elimina.

## Limpieza aplicada (SAFE TO DELETE)

- Eliminado el flujo legacy `update_phase_state` y sus dependencias LLM en `phase_state_updater.py`.
- Eliminado el planner legacy `plan_policy` y scaffolding asociado en `policy_planner.py`.
- Eliminados tests que validaban exclusivamente esos caminos legacy (`test_control_plane`, `test_phase_logic`, `test_precedence`, `test_state_normalization`).

## Qué NO se borró (aunque parezca muerto)

- `backend/negotiation/phase_docs/**` se mantiene como documentación auxiliar hasta confirmar uso.

## Impacto esperado

- Menos complejidad y caminos duplicados en la fase/policy.
- Menos dependencia de LLMs legacy fuera del pipeline híbrido actual.
- Tests más alineados con el flujo real del grafo.
