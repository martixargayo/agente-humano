# 06 — Repo layout y plan de archivos

## 0) Objetivo de integración

Añadir evaluación como capacidad nueva post-cierre, minimizando cambios en código existente y protegiendo el flujo de negociación en caliente.

## 1) Estructura nueva recomendada

```text
backend/
  evaluacion/
    __init__.py
    api/
      __init__.py
      router.py
      models.py
      services.py
    engine/
      __init__.py
      flow_config.py
      job_states.py
      jobs.py
      input_bundle_builder.py
      input_shaping.py
      validators.py
      reconciliation.py
      assembler.py
      provenance.py
      runners/
        __init__.py
        core_runner.py
        trajectory_runner.py
      contracts/
        __init__.py
        feedback_input_bundle_v1.py
        core_runner_input_v1.py
        trajectory_runner_input_v1.py
        feedback_report_core_v1.py
        turn_trajectory_v1.py
        ui_feedback_report_v1.py
    domains/
      __init__.py
      negotiation/
        __init__.py
        extractor.py
        facts.py
        rubric.py
        outcome.py
    prompts/
      core_evaluator_prompt.txt
      trajectory_evaluator_prompt.txt
    storage/
      __init__.py
      base_repository.py
      in_memory_repository.py
      models.py
```

## 2) Archivos existentes a tocar (mínimos)

1. `backend/interfaz_usuario/__init__.py`
   - incluir router de evaluación (`router.include_router(feedback_router)` o import equivalente).
2. `backend/interfaz_usuario_app/app.js`
   - conectar botón `finishNegotiationBtn` a modal+start evaluation+polling.
3. (opcional mínimo) `backend/interfaz_usuario/models.py`
   - solo si se centralizan DTOs de feedback en el paquete `interfaz_usuario`.

## 3) Archivos existentes que NO se tocan deliberadamente

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/pipeline.py`
- `backend/negociacion/nodes/*`
- `backend/negociacion/guards/*`
- contrato actual de `POST /api/interfaz_usuario/negociacion/turn`

Motivo: preservar estabilidad del sistema de conversación y no reintroducir residuos en el flujo crítico.

## 4) Responsabilidades clave nuevas

- `input_bundle_builder.py`: construir `feedback_input_bundle_v1` desde sesión.
- `input_shaping.py`: producir subinputs específicos core/trajectory.
- `reconciliation.py`: reglas de consistencia entre outputs.
- `provenance.py`: hashes, freeze, registro de artefactos.
- `in_memory_repository.py`: implementación v1 estable de persistencia.

## 5) Naming conventions

- contratos versionados con sufijo `_v1`.
- runners con sufijo `_runner.py`.
- funciones de mapping con prefijo `map_`.
- reglas de validación con prefijo `validate_`.

## 6) Por qué no rompe sistema actual

- evaluación se dispara por endpoint separado tras confirmación de cierre,
- no se añade latencia en endpoint de turnos,
- no cambia estructura de `SessionState` operativa,
- no muta `CanonicalState` para almacenar informe.

Ver plan detallado de impacto en `12_repo_change_impact_plan.md`.
