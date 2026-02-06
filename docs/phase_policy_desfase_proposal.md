# Propuesta de implementación: eliminar desfase de fase sin nuevas llamadas LLM

## 0) Prechecks (evidencia)

**Comandos ejecutados (salida resumida se reporta en el mensaje final):**

- `pytest -q`
- `python -m compileall -q backend`

## 1) Diagnóstico del problema actual

**Orden actual (resumen):**

1. `allowed_final` se calcula filtrando por la *phase_state* previa.
2. La LLM propone `phase_candidate` y `policy_id`.
3. La validación/repair opera contra `allowed_final` (basado en fase vieja), generando el desfase.

**Dónde ocurre el filtro por fase (evidencia):**

- En `backend/negotiation/nodes/planner_node.py`:
  - `_allowed_policy_ids_minimal` filtra por fase previa: toma `phase` desde `progress_state.phase_state` y sólo permite policies cuyas fases incluyen esa fase. Esto reduce `allowed_final` antes de la llamada LLM. Luego ese `allowed_final` se pasa a la LLM y también se usa para `repair_policy_by_phase` y `normalize_policy_decision`.
- En `backend/negotiation/policy_planner.py`:
  - `_allowed_policy_ids_minimal` hace el mismo filtro por fase, que luego es usado por `allowed_policy_ids`.

## 2) Cambio principal: allowed SIN filtro por fase

### A) Dónde eliminar el filtro por fase

**Opción preferida:** mover la lógica en `planner_node` y construir `allowed_all` ahí **sin filtrar por fase**, usando los mismos guardrails no relacionados con fase.

**Motivo:** reduce el riesgo de cambios globales y deja `policy_planner` intacto para otras rutas que podrían depender de su comportamiento actual.

### B) Mantener guardrails no relacionados con fase

`allowed_all` debe seguir filtrando por:

- `required_inputs` (usando `_required_inputs_met`).
- hard constraints (`_violates_hard_constraints`).
- otros guardrails existentes no basados en fase.

### C) Catálogo de policies con fases para la LLM

**Requisito:** el prompt debe incluir, para cada policy:

- `policy_id`
- descripción breve
- **phases soportadas**
- required_inputs (si aplica)
- (opcional) resumen del plan

**Helper sugerido:**

- Extender `policy_catalog_text()` o crear `policy_catalog_struct_text()` en `backend/negotiation/policies/registry.py` para incluir phases y required_inputs explícitos por policy (ya contiene phases y required_inputs, pero se puede reforzar con estructura más clara).

### D) Ajuste explícito del prompt

Agregar regla clara en el SYSTEM prompt:

> “Tras elegir phase, SOLO puedes elegir una policy cuya lista de phases incluya esa phase.”

Y añadir en el USER prompt una sección explícita:

```
[Policy catalog with phases]
{policy_catalog_with_phases}
```

## 3) Guardrail post-LLM: coherencia phase↔policy

**Regla principal:** la policy final debe ser coherente con `phase_effective` (fase final tras histeresis).

**Motivo:** `phase_effective` es la fase persistida y la que manda en el sistema.

**Proceso recomendado:**

1. Recibir `phase_candidate` + `policy_decision` desde la LLM.
2. Calcular `phase_effective = postprocess_phase_candidate(...)`.
3. Validar coherencia: `policy_phase_catalog()[policy_id]` contiene `phase_effective`.
4. Si no coherente, usar `repair_policy_by_phase(...)` con:
   - `allowed_all` (sin filtro por fase).
   - `phase_effective`.
   - attempts/constraints si aplica.
5. `normalize_policy_decision(policy_decision, allowed_all)`.

**Importante:** no volver a filtrar `allowed` por fase en ningún punto.

## 4) Pseudocódigo (planner_node)

```python
allowed_all = allowed_policy_ids_no_phase(world_state, belief_state, progress_state, hard_constraints)

phase_candidate, policy_decision = plan_phase_policy(
    allowed_policy_ids=allowed_all,
    policy_catalog_with_phases=policy_catalog_with_phases(),
    ...
)

phase_effective = postprocess_phase_candidate(prev_phase_state, phase_candidate, turn_count)

policy_id_llm = policy_decision["policy_id"]

if phase_effective not in policy_phase_catalog()[policy_id_llm]:
    repaired_id, repair_meta = repair_policy_by_phase(
        policy_id_llm,
        allowed_all,
        policy_phase_catalog(),
        phase_effective,
        preferred_ids=None,
        commitment_level=None,
        policy_attempts=progress_state.get("policy_attempts", {}),
    )
    policy_decision["policy_id"] = repaired_id or policy_id_llm

policy_decision = normalize_policy_decision(policy_decision, allowed_all)
```

## 5) Telemetría / meta para debug

Agregar en `planner_meta` (o `gate_meta`) los campos:

- `allowed_policy_ids_all_count`
- `phase_candidate`
- `phase_effective`
- `policy_id_llm`
- `policy_id_final`
- `policy_phase_mismatch`
- `phase_policy_repair_used`
- `phase_policy_repair_reason`
- `policy_allowed_validation_basis = "allowed_all_no_phase"`

## 6) Impacto en tests (migración)

### A) Tests existentes

Buscar tests que asuman “allowed filtra por phase” y ajustarlos:

- Ahora `allowed_all` **no** depende de phase.
- La coherencia se prueba en `planner_node` con `phase_effective`.

### B) Tests nuevos (diseño)

1. `test_allowed_no_longer_filters_by_phase`
   - mismo `world_state`, fases distintas ⇒ `allowed_all` igual.
2. `test_policy_repaired_when_phase_effective_mismatch`
   - LLM devuelve `phase_candidate=closing` + policy sólo de `opening`.
   - postprocess produce `phase_effective=closing`.
   - assert: policy_final soporta `closing` y `policy_phase_mismatch=True`.
3. `test_hysteresis_hold_forces_policy_to_match_phase_effective`
   - LLM propone `closing` baja confianza, histeresis mantiene `opening`.
   - assert: policy_final soporta `opening`.
4. `test_no_regression_continue_policy_skips_planner`
   - `continue_policy` sigue saltando la LLM.

## 7) Lista de archivos a tocar (propuesta)

- `backend/negotiation/nodes/planner_node.py`
  - construir `allowed_all` sin fase.
  - coherencia post-LLM phase↔policy.
  - meta extra de depuración.
- `backend/negotiation/policy_planner.py` (si se decide mover el cambio allí)
  - quitar filtro por fase en `allowed_policy_ids` o exponer variante `allowed_all_no_phase`.
- `backend/prompts.py`
  - ajustar `PHASE_POLICY_SYSTEM_PROMPT` y `PHASE_POLICY_USER_PROMPT`.
- `backend/negotiation/policies/registry.py`
  - extender catálogo con phases/required_inputs más claros.
- `backend/tests/*`
  - actualizar tests de allowed_by_phase.
  - añadir tests de coherencia phase↔policy.

## 8) Riesgos y mitigaciones

- **Riesgo:** `allowed_all` más grande ⇒ más libertad para LLM.
  - **Mitigación:** prompt explícito + repair determinista + normalize.
- **Riesgo:** policies sin phases configuradas.
  - **Mitigación:** fallback de `repair_policy_by_phase` a `safe_neutral` o `allowed_all[0]`.
- **Riesgo:** tests que dependían del filtro por fase.
  - **Mitigación:** migración de tests + nuevos tests de coherencia.
