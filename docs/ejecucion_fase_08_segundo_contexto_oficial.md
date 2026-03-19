# Ejecución Fase 08 — segundo contexto oficial

## 1. Qué segundo contexto se eligió

Se añadió `validacion_multicontexto` con `public_slug="negociacion-validacion"`.

No se ha presentado como un caso pedagógico completamente nuevo. Es, de forma honesta, un **contexto oficial de validación multi-context** derivado del baseline actual para demostrar que toda la infraestructura ya soporta más de un contexto real del mismo flow `negociacion`.

## 2. Si es un contexto real del repo o un contexto de validación multi-context

Es un **contexto de validación multi-context**.

La razón es que en el repo no existía un segundo bundle listo y coherente del mismo flow. En vez de inventar un rediseño del motor o un caso pedagógico nuevo, se creó un segundo bundle oficial completo, con identidad, slug, assets y evaluación propios, pero manteniendo la misma semántica negociadora del baseline.

## 3. Qué archivos concretos se crearon

### Nuevo contexto oficial

- `backend/negociacion/contexts/validacion_multicontexto/manifest.json`
- `backend/negociacion/contexts/validacion_multicontexto/prompts/*`
- `backend/negociacion/contexts/validacion_multicontexto/assets/*`
- `backend/negociacion/contexts/validacion_multicontexto/evaluation/*`

### Validación de la fase

- `backend/tests/test_phase8_second_official_context.py`
- `backend/scripts/check_phase8_second_official_context.py`
- `docs/ejecucion_fase_08_segundo_contexto_oficial.md`

## 4. Qué archivos existentes se tocaron y por qué

- `backend/negociacion/contexts/resolver.py`
  - para dejar de asumir que solo existe `baseline_current` y permitir resolver bundles oficiales adicionales.
- `backend/negociacion/contexts/public_mapping.py`
  - para resolver `public_slug -> context_id` de forma genérica.
- `backend/negociacion/contexts/__init__.py`
  - para exportar helpers de resolución usados por runtime/tests.
- `backend/negociacion/orchestration/flow_config.py`
  - cambio mínimo imprescindible para que el runtime use `prompts_dir` y assets del contexto ligado a la sesión.
- `backend/negociacion/state/canonical_state.py`
  - cambio mínimo imprescindible para que el estado canónico inicial cargue `persona` y `negotiation_brief` del contexto oficial correcto.
- `backend/interfaz_usuario/services.py`
  - para construir el runtime usando el `context_id` ya ligado a la sesión.
- `backend/negociacion/optimizador/services.py`
  - para que el sandbox optimizer construya la config base sobre el contexto oficial correcto.
- `backend/negociacion/optimizador/prompts_bridge.py`
- `backend/negociacion/optimizador/experiments_bridge.py`
  - cambios mínimos necesarios para que los overrides del optimizer se apliquen sobre el bundle base del contexto oficial seleccionado y no siempre sobre el baseline global.

## 5. Qué NO hizo falta tocar

No hizo falta tocar:

- fases de negociación;
- `CanonicalState` táctico más allá de la carga inicial de assets;
- `finish_button_armed`;
- nodos `memory / phase_classifier / planner / executor`;
- guards;
- prompts baseline;
- frontend público;
- evaluación estructural;
- rediseño del optimizer.

## 6. Cómo quedó soportado por capa

### URL pública

- sigue funcionando `/interfaz_usuario`
- sigue funcionando `/interfaz_usuario/negociacion`
- ahora funciona `/interfaz_usuario/negociacion-validacion`
- también con slash final

### Sesión

- `context_id=validacion_multicontexto` fija el nuevo contexto en `world_state["negotiation_context"]`
- `public_slug=negociacion-validacion` resuelve al mismo contexto
- sigue existiendo la política conservadora de conflicto y no hay mezcla silenciosa

### Runtime

- la config del pipeline ahora usa el `prompts_dir` del contexto ligado a la sesión
- la carga de `phase_cards` / `phase_classifier_card` se resuelve contra el contexto efectivo
- el estado canónico inicial carga `persona` y `negotiation_brief` del contexto oficial correcto
- las trazas siguen reflejando `context_id` correcto porque ya usaban el binding de sesión

### Trazas

- no hubo que rediseñarlas
- el `context_meta` ya estaba preparado y ahora recibe también el segundo contexto oficial real

### Evaluación

- no hubo que rediseñar evaluación
- al existir un bundle `evaluation/` real para el segundo contexto, `DomainContext`, prompts y rúbrica se resuelven correctamente contra ese contexto
- provenance y artifacts siguen reflejando `flow_id/context_id/context_version`

### Optimizer

- bootstrap explícito del nuevo contexto funciona
- clone y new conversation lo heredan
- `run_sandbox_turn()` conserva `base_context`
- los overrides siguen viviendo por encima del contexto oficial base
- se corrigió el hueco real donde los overrides se copiaban siempre desde prompts baseline globales

## 7. Por qué baseline no se rompe

- `baseline_current` sigue siendo el default
- su `public_slug` sigue siendo `negociacion`
- los tests previos de sesión, superficie pública, trazas, evaluación y optimizer siguen pasando
- no se ha cambiado la semántica del flow ni el motor, solo la resolución del bundle oficial efectivo

## 8. Tests corridos

- `python -m pytest backend/tests/test_phase8_second_official_context.py -q`
- `python -m pytest backend/tests/test_phase3_context_session_binding.py backend/tests/test_phase4_public_context_surface.py backend/tests/test_phase5_context_traces.py backend/tests/test_phase6_evaluation_context_aware.py backend/tests/test_phase7_optimizer_context_aware.py backend/tests/test_phase8_second_official_context.py -q`
- `PYTHONPATH=backend python backend/scripts/check_phase8_second_official_context.py`

## 9. Limitaciones honestas de esta fase

- `validacion_multicontexto` no pretende ser un nuevo producto pedagógico completo; es un bundle oficial de validación infra.
- No se ha añadido selector visual avanzado de contexto.
- No se ha introducido un tercer contexto ni multi-context complejo en UI.
- No se ha rediseñado evaluación ni optimizer; solo se corrigieron los puntos mínimos que aún estaban fijados al baseline.
- La fase demuestra soporte real para más de un contexto oficial del mismo flow, pero no convierte todavía al sistema en una plataforma general de context packs arbitrarios sin más validación futura.
