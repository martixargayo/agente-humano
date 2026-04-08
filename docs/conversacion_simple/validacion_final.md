# Validación comparativa final: `conversacion_simple` vs `negociacion`

## Alcance
Fase dedicada a validación/auditoría comparativa basada en tests automatizados.

## Clasificación
- **Idéntico (externo):** bootstrap/finalize envelope y conflictos de contexto de sesión.
- **Equivalente (externo):** contrato visible de `turn` y metadatos de sesión/superficie.
- **Divergente deliberado (interno):** topología de traces (`memory/phase/planner/executor` vs `brain`), forma interna del canonical state y mantenimiento de memoria.
- **Gap real detectado:** comparación cross-flow en optimizador no soportada; se mantiene fallo explícito y controlado.

## Evidencia
Ver suites:
- `test_conversacion_simple_vs_negociacion_api_compat.py`
- `test_conversacion_simple_vs_negociacion_trace_contracts.py`
- `test_conversacion_simple_vs_negociacion_optimizer_contracts.py`
- `test_conversacion_simple_vs_negociacion_long_run_validation.py`
