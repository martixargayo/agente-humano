# Negotiation Context Execution — Definitive Implementation Plan

## 1) Executive summary

El problema confirmado no es un bug puntual en un nodo, sino una **falla de contrato de entrada**: hoy existen múltiples fuentes de verdad contextual (`session binding`, `config/prompts`, `trace/meta`, y en rutas legacy incluso default implícito) que pueden divergir dentro del mismo turno.

Objetivo final de esta fase: **UN TURNO = UN SOLO CONTEXTO EFECTIVO COHERENTE**.

Criterio rector operativo:

- Antes de ejecutar builders/planner/executor, el runtime debe haber fijado un único `effective_context_id`.
- En rutas stateful, ese valor debe quedar alineado con sesión, config y trace.
- Si no hay alineación, se bloquea con error de dominio y la capa API traduce a HTTP (409/400 según el caso).

Por qué la solución es contractual y no un parche local:

- El skew observado aparece en `load_state.before` (temprano) y luego se propaga al pipeline completo.
- Corregir solo `prompt_io_mapping` o solo `phase_cards` no elimina la raíz; solo la disfraza.
- La corrección real exige un contrato explícito de ejecución por turno (`TurnExecutionContext`) + validador central pre-ejecución.

---

## 2) Scope y non-goals

### Scope (esta fase)

1. Introducir `TurnExecutionContext` como contrato obligatorio de ejecución en paths stateful.
2. Introducir errores de dominio contextual (sin `HTTPException` en orchestration).
3. Introducir validador único pre-ejecución (`validate_turn_context_pre_execution(...)`).
4. Reencaminar `/negociar` para no usar contexto implícito stateful.
5. Forzar `build_negotiation_pipeline_config(context_id=...)` en paths stateful.
6. Consolidar trazabilidad contextual mínima obligatoria.

### Non-goals (explícitos)

1. No multicontexto concurrente por sesión.
2. No namespacing de `canonical_state` por contexto.
3. No migración implícita de contexto en sesión existente.
4. No rediseño profundo de prompts ni de contenido de cards.
5. No cambio de semántica de `prompt_io_mapping` más allá de subordinarlo al contexto validado.

---

## 3) Evidence base / factual diagnosis

1. **Ruta productiva rota confirmada**:
   - `POST /negociar` (`backend/api/app.py`) llama `run_negotiation_agent(state, message)`.
   - `run_negotiation_agent` (`backend/negociacion/pipeline.py`) llama `build_negotiation_pipeline_config()` sin `context_id`.
   - Resultado: contexto baseline implícito en path stateful, potencialmente distinto al ya ligado a sesión.

2. **Ruta estructural vulnerable**:
   - `execute_turn_with_contract(...)` (`backend/negociacion/orchestration/turn_contract.py`) hoy no impone invariante fuerte entre contextos efectivos/config/sesión antes de ejecutar runtime.

3. **Rutas ya más sanas**:
   - `interfaz_usuario/services.py` y `optimizador/services.py` llaman `ensure_session_context(...)` y construyen config con `context_id` explícito.
   - Ya existen 409 en conflictos de binding de sesión.

4. **Primer punto observable del skew**:
   - Divergencia temprana en `load_state.before` cuando requested/config/prompts context ≠ `session_bound_context_id`.

5. **Por qué `prompt_io_mapping` no es raíz**:
   - Es transformador de shape de IO.
   - No determina fuente de verdad contextual ni binding de sesión.
   - El mismatch aparece antes, en resolución/entrada de contexto y construcción de config.

---

## 4) Architecture target

Modelo objetivo de source-of-truth:

- El caller de superficie construye `TurnExecutionContext`.
- `TurnExecutionContext` fija `effective_context_id` (obligatorio en stateful).
- Config stateful se construye desde `effective_context_id`.
- El validador pre-ejecución verifica invariante dura antes de entrar al runtime.
- Trace se llena con el mismo contexto validado (no inferido tardíamente desde default).

Invariante obligatoria (stateful):

```text
effective_context_id == session_bound_context_id == config_context_id == trace_context_id
```

Si falla cualquier igualdad: bloqueo pre-builder.

---

## 5) Stateful vs non-stateful execution model

### Definición formal

**Stateful execution**: cualquier ejecución que lee/escribe estado de sesión (`SessionState`) persistente, histórico de trazas, canonical state, o usa lock de sesión.

**Non-stateful execution**: ejecución aislada (eval/dev/scripts) sin compromiso de sesión productiva ni continuidad de conversación persistida.

### Restricciones

#### Stateful

- Requiere `TurnExecutionContext` completo.
- Prohibido default implícito de contexto.
- Requiere validación pre-ejecución.
- `build_negotiation_pipeline_config` debe recibir `context_id` explícito.

#### Non-stateful

- Puede usar `build_negotiation_pipeline_config()` sin `context_id` por compatibilidad controlada.
- Debe declararse explícitamente como `execution_mode="non_stateful"` en helpers nuevos.
- No puede escribir a sesiones productivas con contexto implícito.

---

## 6) TurnExecutionContext design

Decisión cerrada de ubicación (ambigüedad resuelta): `TurnExecutionContext` vive **únicamente** en `backend/negociacion/orchestration/turn_execution_context.py`.
Justificación: su uso canónico está en la frontera de ejecución (`execute_turn_with_contract` + validador pre-ejecución), no en resolución de catálogo de contextos.
Regla: `contexts/*` no define ni reexporta `TurnExecutionContext`; solo lo consume orchestration/services.

## Módulo nuevo propuesto

`backend/negociacion/orchestration/turn_execution_context.py`

### Shape propuesto (exacto)

```python
from dataclasses import dataclass
from typing import Literal

ExecutionMode = Literal["stateful", "non_stateful"]

@dataclass(frozen=True)
class TurnExecutionContext:
    # Identity
    user_id: str | None
    session_id: str | None

    # Contract
    execution_mode: ExecutionMode
    effective_context_id: str | None

    # Provenance
    requested_context_id: str | None
    session_bound_context_id: str | None
    context_source: Literal[
        "interfaz_usuario_bootstrap",
        "interfaz_usuario_session_bound",
        "optimizador_session_bound",
        "api_negociar_explicit",
        "internal_non_stateful_default",
        "internal_explicit",
    ]

    # Surface metadata
    entry_surface: str
    entrypoint: str

    # Optional diagnostics
    # context_version is observability-only in this phase (no hard-block by itself)
    context_version: str | None = None
    flow_id: str | None = None
```

### Campos obligatorios

- Stateful: `execution_mode`, `effective_context_id`, `entry_surface`, `entrypoint`, `session_id`.
- Non-stateful: `execution_mode`, `entry_surface`, `entrypoint`.

### Campos derivados

- `session_bound_context_id` viene de `read_bound_context_from_session(state)`.
- `context_version` y `flow_id` se derivan de `resolve_negotiation_context(effective_context_id)`.
- `context_version` **no forma parte de la invariante dura en esta fase**: se persiste en trazas y se marca drift, pero no bloquea por sí sola.

### Helpers/constructores por surface (obligatorios)

1. `build_interfaz_usuario_turn_context(...)` en `backend/interfaz_usuario/services.py`.
2. `build_optimizador_turn_context(...)` en `backend/negociacion/optimizador/services.py`.
3. `build_api_negociar_turn_context(...)` en módulo de servicio compartido nuevo:
   - `backend/negociacion/services/turn_context_factory.py`.

Regla: ningún caller productivo construye `TurnExecutionContext` “a mano”.

### Lifecycle durante el turno

1. Surface resuelve/bindea sesión-contexto.
2. Surface construye `TurnExecutionContext`.
3. Surface construye config con `context_id=turn_ctx.effective_context_id`.
4. `execute_turn_with_contract(..., turn_context=...)` valida pre-ejecución.
5. Runtime ejecuta.
6. Trace guarda snapshot contextual validado.

---

## 7) Domain errors / exception model

## Módulo nuevo propuesto

`backend/negociacion/orchestration/context_errors.py`

### Errores de dominio

- `ContextContractError(RuntimeError)` (base)
- `MissingTurnContextError(ContextContractError)`
- `ImplicitContextForbiddenError(ContextContractError)`
- `ContextMismatchError(ContextContractError)`
- `StatefulContextRequiredError(ContextContractError)`
- `InvalidConfigContextError(ContextContractError)`

Cada error incluye atributos estructurados (`reason_code`, `expected`, `actual`, `entry_surface`, `entrypoint`).

### Traducción HTTP (solo API/services)

- `MissingTurnContextError` → 400 (`missing_turn_context`)
- `ImplicitContextForbiddenError` → 400 (`implicit_context_forbidden`)
- `ContextMismatchError` → 409 (`context_mismatch`)
- `StatefulContextRequiredError` → 400 (`stateful_context_required`)
- `InvalidConfigContextError` → 500 (`invalid_config_context`) si es bug interno

Regla obligatoria: **orchestration/pipeline no importa `HTTPException`**.

---

## 8) Pre-execution validation contract

Validador único propuesto:

- Archivo: `backend/negociacion/orchestration/turn_context_validator.py`
- Firma:

```python
def validate_turn_context_pre_execution(
    *,
    state: SessionState,
    config: NegotiationTurnConfig,
    turn_context: TurnExecutionContext,
) -> ValidatedTurnContext:
    ...
```

`ValidatedTurnContext` (dataclass) incluirá:

- `effective_context_id`
- `session_bound_context_id`
- `config_context_id`
- `trace_context_id` (igual a effective, preasignado para trace)
- `reason_codes: list[str]` (incluye `ctx_precheck_ok`)

### Qué compara

1. `turn_context.execution_mode`.
2. Si stateful: existencia de `effective_context_id`.
3. Si stateful: `session_bound_context_id` de sesión vs `effective_context_id`.
4. `config_context_id` derivado desde config (estrategia cerrada abajo) vs `effective_context_id`.
5. `context_version`: solo diagnóstico de drift (warning con reason code), sin bloqueo en esta fase.

### Estrategia cerrada para `config_context_id` (decisión final)

- **Fuente primaria**: nuevo campo en config `context_id: str | None` (agregado a `NegotiationTurnConfig`).
- **Validación cruzada**: `resolve_context_for_prompts_dir(config.prompts_dir)` debe devolver mismo `context_id` en stateful.
- Si no coincide: `InvalidConfigContextError`.

Esta decisión evita depender de inferencia manual en cada caller.

### Dónde se invoca

1. `execute_turn_with_contract(...)` (invocación obligatoria).
2. `run_negotiation_agent(...)` en modo compat/dev (si se mantiene).
3. Cualquier nuevo wrapper stateful.

### Qué bloquea

- Cualquier mismatch antes de cargar cards/builders.
- Cualquier stateful sin contexto explícito.
- Cualquier config con contexto ambiguo.
- `context_version` faltante o drift aislado **no bloquea** en esta fase (solo observabilidad).

### Qué traza

- evento `turn_context_precheck`
- `reason_codes`
- quartet: `effective/bound/config/trace`

---

## 9) File-by-file implementation plan

### 9.1 `backend/api/app.py`

**Situación actual**: `/negociar` usa `run_negotiation_agent` sin contexto explícito.

**Problema**: path stateful ambiguo con baseline implícito.

**Cambio concreto**:

1. Extender payload de `/negociar` para requerir `context_id` explícito en esta fase.
2. Delegar a nuevo servicio `negociacion.services.legacy_negociar_service.run_legacy_negociar_turn(...)`.
3. Traducir errores de dominio contextual a 400/409.

**Funciones afectadas**:

- `negociar_endpoint`.
- `NegociarRequest` (modelo separado de `ChatRequest` para no romper `/chat`).

**Compat impact**:

- Breaking change controlado en `/negociar`: llamadas sin `context_id` pasan a 400.

---

### 9.2 `backend/negociacion/pipeline.py`

**Situación actual**: `run_negotiation_agent(state, message)` sin contrato contextual.

**Problema**: entrypoint ambiguo productivo.

**Cambio concreto**:

1. Marcar como compat/dev interno.
2. Cambiar firma a:

```python
def run_negotiation_agent(
    state: SessionState,
    user_message: str,
    *,
    context_id: str,
    execution_mode: Literal["stateful", "non_stateful"] = "stateful",
) -> Tuple[str, SessionState]
```

3. En `stateful`, exigir `context_id` y ejecutar validador.
4. Si se llama sin contexto (vía compat wrapper), lanzar `ImplicitContextForbiddenError`.

**Compat impact**:

- scripts/evals que usen versión antigua deben migrar a explicit context o marcar `non_stateful`.

---

### 9.3 `backend/negociacion/orchestration/turn_contract.py`

**Situación actual**: recibe `TurnEntryContract`; no recibe contexto de turno explícito.

**Problema**: precheck contextual no centralizado.

**Cambio concreto**:

1. Extender firma:

```python
def execute_turn_with_contract(..., turn_context: TurnExecutionContext) -> ...
```

2. Invocar `validate_turn_context_pre_execution` antes de `run_negotiation_cognitive_turn`.
3. Pasar resultado validado a trazas/meta.

**Funciones afectadas**:

- `execute_turn_with_contract`.
- helper nuevo `_build_entry_contract_snapshot(...)` recomendado para reducir duplicación.

**Compat impact**:

- todos los callers de `execute_turn_with_contract` deben pasar `turn_context`.

---

### 9.4 `backend/negociacion/orchestration/flow_config.py`

**Situación actual**: `build_negotiation_pipeline_config(context_id: str|None=None)` permite default implícito, y `NegotiationTurnConfig` no tiene `context_id` explícito.

**Problema**: no hay `config_context_id` fuerte para validar.

**Cambio concreto**:

1. Agregar campo `context_id: str | None` a `NegotiationTurnConfig`.
2. En `build_negotiation_pipeline_config`:
   - si `context_id` explícito: resolver y setear `config.context_id`.
   - si no explícito: mantener legacy para non-stateful, setear `config.context_id` al default resuelto.
3. Agregar helper:

```python
def derive_config_context_id(config: NegotiationTurnConfig) -> str | None
```

que valida `context_id` vs `prompts_dir` mediante `resolve_context_for_prompts_dir`.

**Compat impact**:

- bajo; campo nuevo aditivo en config.

---

### 9.5 `backend/interfaz_usuario/services.py`

**Situación actual**: ya respeta binding/contexto en gran parte.

**Problema**: falta contrato formal `TurnExecutionContext` y traducción de errores de dominio nuevos.

**Cambio concreto**:

1. Agregar helper local:

```python
def build_interfaz_usuario_turn_context(*, state: SessionState, entrypoint: str, requested_context_id: str | None = None) -> TurnExecutionContext
```

2. En `run_turn(...)`, construir `turn_context` y pasarlo a `execute_turn_with_contract`.
3. Mantener 409 existente para conflicto de contexto de sesión (traducido desde error de dominio).

**Compat impact**:

- no breaking para clientes de interfaz_usuario.

---

### 9.6 `backend/negociacion/optimizador/services.py`

**Situación actual**: construye config con `base_context["context_id"]`.

**Problema**: falta contrato formal único y validación central antes de ejecutar.

**Cambio concreto**:

1. Agregar helper local:

```python
def build_optimizador_turn_context(*, state: SessionState, entrypoint: str, optimizer_session_id: str) -> TurnExecutionContext
```

2. En `run_sandbox_turn(...)`, pasar `turn_context` a `execute_turn_with_contract`.
3. Mantener overrides, pero explícitamente subordinados a `turn_context.effective_context_id`.

**Compat impact**:

- no breaking externo; interno sí para firma de execute.

---

### 9.7 `backend/negociacion/optimizador/context_bridge.py`

**Situación actual**: mezcla resolución de contexto y HTTPException.

**Problema**: acoplamiento API en capa de dominio puente.

**Cambio concreto**:

1. Reemplazar `HTTPException` por errores de dominio contextual.
2. Mantener forma de retorno, pero delegar traducción HTTP al router/services.
3. Exportar helper reutilizable para construir bloque base (`flow_id/context_id/context_version`) para `TurnExecutionContext`.

**Compat impact**:

- cambio interno; routers adaptan try/except.

---

### 9.8 `backend/negociacion/contexts/session_binding.py`

**Situación actual**: `ensure_session_context` lanza `HTTPException` 409.

**Problema**: capa de dominio acoplada a FastAPI.

**Cambio concreto**:

1. Cambiar a error de dominio (`ContextMismatchError` o `SessionContextConflictError` especializado).
2. Mantener API de función.
3. No introducir migración implícita jamás.

**Compat impact**:

- todos los callers que hoy esperan HTTPException deben traducir en services/api.

---

### 9.9 `backend/negociacion/traces/context_meta.py`

**Situación actual**: si no hay binding, cae a default context implícito.

**Problema**: puede ocultar divergencia en paths stateful.

**Cambio concreto**:

1. Cambiar firma a:

```python
def build_trace_context_meta(*, validated_context: ValidatedTurnContext, overrides_applied: bool = False) -> TraceContextMeta
```

2. Eliminar fallback implícito en stateful.
3. Permitir fallback solo en non-stateful explícito.

**Compat impact**:

- ajusta callers de tracing en runtime y optimizador.

---

### 9.10 Nuevo módulo `backend/negociacion/orchestration/turn_execution_context.py`

**Situación actual**: no existe contrato explícito.

**Cambio concreto**:

- Definir `TurnExecutionContext`, `ExecutionMode`, utilidades de normalización.

---

### 9.11 Nuevo módulo `backend/negociacion/orchestration/turn_context_validator.py`

**Situación actual**: no existe validador central.

**Cambio concreto**:

- Definir `ValidatedTurnContext` + `validate_turn_context_pre_execution(...)`.

---

### 9.12 Nuevo módulo `backend/negociacion/orchestration/context_errors.py`

**Situación actual**: errores HTTP mezclados en dominio.

**Cambio concreto**:

- Definir jerarquía de errores de contrato contextual.

---

### 9.13 Nuevo módulo `backend/negociacion/services/turn_context_factory.py`

**Situación actual**: construcción dispersa por caller.

**Cambio concreto**:

- Centralizar constructores compartidos para surfaces y `/negociar` legacy.

---

### 9.14 Nuevo módulo `backend/negociacion/services/legacy_negociar_service.py`

**Situación actual**: `/negociar` llama pipeline legacy directamente.

**Cambio concreto**:

- Servicio explícito para la remediación de `/negociar` con contrato contextual estricto.

---

### 9.15 Otros archivos a ajustar

- `backend/negociacion/__init__.py` y exports de módulos nuevos.
- tests existentes que llamen `build_negotiation_pipeline_config()` en modo stateful sin `context_id`.
- scripts forenses para convertir hallazgos en regresiones de contrato.

---

## 10) Surface-by-surface behavior

### Interfaz por URL (`/api/interfaz_usuario/...`)

- Bootstrap define/bindea contexto de sesión (ya existente).
- Turno construye `TurnExecutionContext` con source `interfaz_usuario_session_bound`.
- Config se construye con `bound_context.context_id`.
- Precheck obligatorio; mismatch imposible de pasar.

### Optimizador (`/api/optimizador/...`)

- Sesión sandbox queda ligada a contexto base.
- Turno construye `TurnExecutionContext` con source `optimizador_session_bound`.
- Overrides no pueden cambiar `effective_context_id`.
- Precheck obligatorio.

### `/negociar` legacy

- En esta fase deja de ser implícito.
- Requiere `context_id` explícito en payload.
- Si sesión ya está ligada a otro contexto, responde 409.
- Si falta `context_id`, responde 400.

### Callers internos

- Stateful internos: deben pasar por factory y `execute_turn_with_contract(..., turn_context=...)`.
- Wrappers intermedios: deprecados si no pueden construir contexto explícito.

### Eval/dev

- Permitidos non-stateful con default controlado.
- Recomendado pasar `context_id` explícito también en evals para determinismo.

---

## 11) Legacy `/negociar` remediation plan

Decisión operacional cerrada para esta fase:

1. `/negociar` permanece disponible temporalmente por compatibilidad.
2. Modelo exacto de entrada (`backend/api/app.py`):

```python
class NegociarRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    context_id: str | None = None
```

`context_id` se trata como **obligatorio de negocio** aunque técnicamente nullable para devolver 400 semántico (no 422 de validación genérica).

3. Request JSON esperado:

```json
{
  "user_id": "...",
  "session_id": "...",
  "message": "...",
  "context_id": "..."
}
```

4. Comportamiento:
   - `context_id` ausente/vacío → **400** `missing_context_id_for_stateful_negociar`.
   - sesión ligada a contexto distinto → **409** `session_context_conflict`.
   - válido → ejecuta por mismo contrato contextual que surfaces sanas.
5. Endpoint marcado como `deprecated=True` + header deprecación en éxito (`X-Legacy-Negociar: deprecated_use_interfaz_usuario_or_optimizador`).

Esta opción contiene riesgo sin romper de inmediato todo cliente legacy, y elimina implícito ya en PR de contención.

---

## 12) `run_negotiation_agent` future status

- Estado: **deprecated para uso productivo stateful implícito**.
- Firma futura: requiere `context_id` explícito (ver sección 9.2).
- Uso permitido:
  - dev/internal controlado,
  - eval wrappers explícitos.
- Uso que debe fallar:
  - cualquier path stateful sin `context_id`.

---

## 13) Observability and trace contract

Campos mínimos obligatorios por turno (trace root + `_entry_contract`):

- `effective_context_id`
- `session_bound_context_id`
- `config_context_id`
- `trace_context_id`
- `context_source`
- `execution_mode`
- `context_precheck_passed: bool`
- `context_reason_codes: list[str]`

Reason codes cerrados (v1):

- `ctx_precheck_ok`
- `ctx_missing_turn_context`
- `ctx_stateful_requires_explicit`
- `ctx_session_not_bound`
- `ctx_bound_effective_mismatch`
- `ctx_config_effective_mismatch`
- `ctx_config_prompts_unresolvable`
- `ctx_trace_assignment_failed`
- `ctx_implicit_forbidden`

Event/stage names:

- `turn_context_resolved`
- `turn_context_precheck`
- `turn_context_blocked`
- `turn_context_trace_attached`

Regla anti-ocultamiento:

- trace no puede “inventar default” en stateful.
- si no hay datos coherentes, se bloquea antes y se traza `turn_context_blocked`.

---

## 14) Test strategy

### Unit

1. `turn_context_validator`:
   - happy path stateful coherente.
   - missing context en stateful.
   - mismatch bound/effective.
   - mismatch config/effective.
2. `derive_config_context_id`:
   - `config.context_id` + `prompts_dir` coherentes.
   - conflicto entre ambos.

### Integration

1. `execute_turn_with_contract` bloquea antes de runtime con mismatch.
2. `build_trace_context_meta` consume `ValidatedTurnContext` y refleja quartet coherente.

### Route/API

1. `/api/interfaz_usuario/negociacion/turn` mantiene comportamiento sano.
2. `/api/optimizador/sandbox/turn` mantiene comportamiento sano con contrato formal.
3. `/negociar`:
   - 400 sin `context_id`.
   - 409 con conflicto sesión/contexto.
   - 200 con contexto válido.

### Regression/forensics

Convertir scripts forenses actuales en regresiones asertivas de contrato:

- `forensics_context_skew_first_divergence` debe demostrar skew imposible post-fix.
- `forensics_runtime_broken_route_map` debe validar que `/negociar` ya no usa ruta implícita.

### Contract tests

- tests que validen explícitamente invariante:

```text
effective == session_bound == config == trace
```

sobre el último trace en cada surface stateful.

---

## 15) PR-by-PR rollout plan

## PR1 — Contención mínima segura (obligatorio primero)

1. Introducir errores de dominio (`context_errors.py`).
2. Desacoplar `HTTPException` de `session_binding.py` y `optimizador/context_bridge.py`.
3. Remediar `/negociar` para requerir `context_id` y traducir errores en API.
4. Añadir tests API de 400/409 en `/negociar`.

**Riesgo**: romper clientes legacy sin `context_id`.
**Mitigación**: comunicar contrato + header deprecación + release notes.

## PR2 — Formalización contractual completa

1. Crear `TurnExecutionContext` + factory compartida.
2. Crear `turn_context_validator` y `ValidatedTurnContext`.
3. Extender `execute_turn_with_contract(..., turn_context=...)`.
4. Añadir `context_id` en `NegotiationTurnConfig` y validación cruzada con `prompts_dir`.
5. Migrar interfaz_usuario y optimizador al nuevo contrato.

**Riesgo**: impacto transversal por cambio de firma.
**Mitigación**: cambios mecánicos + tests de integración por surface.

## PR3 — Cleanup, deprecaciones y observabilidad final

1. Deprecar formalmente `run_negotiation_agent` implícito.
2. Unificar trace/meta contextual con reason codes cerrados.
3. Migrar scripts/tests forenses a regresión contractual.
4. Documentación de operación y runbook de incidentes de contexto.

**Riesgo**: ruido en telemetría inicial.
**Mitigación**: dashboards temporales + sampling.

---

## 16) Risks / compatibility / migration

1. **Breaking en `/negociar`**: requiere `context_id`.
   - Mitigación: período de deprecación corto + mensaje claro de error.

2. **Callers internos legacy** a `run_negotiation_agent`.
   - Mitigación: compat wrapper temporal que falle explícitamente en stateful sin contexto.

3. **Tests/scripts antiguos** que asumían default implícito.
   - Mitigación: etiquetar como `non_stateful` o pasar `context_id`.

4. **Errores 409 más frecuentes al principio** por detectar conflictos reales antes ocultos.
   - Mitigación: observabilidad con reason codes + guía de corrección por cliente.

Feature flag: no requerido para la invariante; se recomienda activación directa para evitar doble comportamiento.

---

## 17) Acceptance criteria

La implementación se considera aceptada solo si se cumple:

1. En todo path stateful productivo, no existe ejecución sin `TurnExecutionContext`.
2. `/negociar` no ejecuta stateful implícito nunca.
3. `build_negotiation_pipeline_config()` sin `context_id` no se usa en stateful.
4. Invariante `effective==bound==config==trace` verificada por tests en surfaces stateful.
5. `HTTPException` no aparece en orchestration/pipeline/context domain modules.
6. `prompt_io_mapping` no actúa como source-of-truth contextual en ninguna ruta.
7. Forensics/regresiones no detectan primer skew en `load_state.before` para paths corregidos.
8. `TurnExecutionContext` existe en una única ubicación (`orchestration/turn_execution_context.py`) sin duplicados conceptuales.
9. `context_version` queda trazado y persistido; drift no bloquea por sí solo en esta fase.

---

## 18) Appendix

### 18.1 Inventario de callers relevantes

#### Productivos stateful

- `backend/interfaz_usuario/services.py::run_turn`
- `backend/negociacion/optimizador/services.py::run_sandbox_turn`
- `backend/api/app.py::negociar_endpoint` (legacy, a remediar)

#### Wrappers intermedios

- `backend/negociacion/orchestration/turn_contract.py::execute_turn_with_contract`
- `backend/negociacion/pipeline.py::run_negotiation_agent`

#### Evals/scripts/dev (mayormente non-stateful)

- `backend/negociacion/evals/runners/*`
- `backend/scripts/check_*`
- `backend/scripts/forensics_*`

### 18.2 Reason codes propuestos (tabla rápida)

- `ctx_precheck_ok`: contrato válido.
- `ctx_missing_turn_context`: faltó objeto de contexto de turno.
- `ctx_stateful_requires_explicit`: stateful sin contexto explícito.
- `ctx_bound_effective_mismatch`: sesión ligada ≠ efectivo.
- `ctx_config_effective_mismatch`: config ≠ efectivo.
- `ctx_config_prompts_unresolvable`: prompts_dir no resolvió contexto oficial.
- `ctx_implicit_forbidden`: caller intentó default implícito en stateful.

### 18.3 Pseudo-signatures operativas

```python
# orchestration/turn_contract.py
execute_turn_with_contract(
    *,
    state: SessionState,
    user_message: str,
    config: NegotiationTurnConfig,
    contract: TurnEntryContract,
    turn_context: TurnExecutionContext,
) -> tuple[str, SessionState, dict[str, Any]]

# orchestration/turn_context_validator.py
validate_turn_context_pre_execution(
    *,
    state: SessionState,
    config: NegotiationTurnConfig,
    turn_context: TurnExecutionContext,
) -> ValidatedTurnContext

# services/legacy_negociar_service.py
run_legacy_negociar_turn(
    *,
    user_id: str,
    session_id: str,
    message: str,
    context_id: str,
) -> dict[str, Any]
```

### 18.4 Decisiones cerradas en este documento

1. `config_context_id` se obtiene de `config.context_id` + validación cruzada con `prompts_dir`.
2. `/negociar` en esta fase se mantiene pero **obliga `context_id` explícito** (no alternativa).
3. Excepciones HTTP quedan exclusivamente en API/services; orchestration solo usa errores de dominio.
4. `TurnExecutionContext` vive únicamente en `orchestration/turn_execution_context.py`.
5. `context_version` se usa para trazabilidad y detección de drift, no como condición de bloqueo duro en esta fase.
