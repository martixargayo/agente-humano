# 02 · Gap analysis — `negociacion` vs `conversacion_simple`

## 1) Reutilización tal cual (sin cambios conceptuales)

Estas piezas deberían preservarse prácticamente idénticas:

1. **Session lifecycle + locks + TTL**
   - `backend/sessions/lifecycle.py`
   - `backend/sessions/session_lock.py`
   - `backend/sessions/surface_scope.py`
2. **Contrato de contexto y prechecks**
   - `backend/negociacion/contexts/*`
   - `backend/negociacion/orchestration/turn_context_validator.py`
   - `backend/negociacion/orchestration/turn_contract.py`
3. **Error translation HTTP de contrato contextual**
   - `backend/negociacion/services/context_http.py`
4. **Filosofía de contextos oficiales y public slug**
   - manifests + resolver + public mapping
5. **Capa de presentation contextual**
   - `backend/interfaz_usuario/presentation_resolver.py`

## 2) Reutilización con adaptación

1. **Flow config y runtime orchestration**
   - hoy está acoplado a 4 nodos en `flow_config.py`.
   - debe extraerse un patrón reusable para múltiples topologías de flujo.
2. **Trace model / observabilidad**
   - mantener envelope de trace, pero adaptar secciones de nodos (de 4 a 1).
3. **Prompt IO mapping**
   - reusar motor, adaptar reglas al output del nodo único.
4. **Optimizador**
   - reusar UX/contratos, pero ajustar la semántica de overrides al nuevo prompt/contrato.

## 3) Piezas que sobran o quedan fuera de `conversacion_simple` online

1. `phase_classifier` como llamada separada.
2. `executor` como llamada separada.
3. `memory` como llamada separada en el camino crítico.

> Nota: sus responsabilidades funcionales no “sobran”, solo dejan de existir como nodos online independientes.

## 4) Piezas a abstraer para evitar duplicación

1. **Builder de config por flujo**
   - `build_negotiation_pipeline_config` hoy es específico de `negociacion`.
2. **`TurnExecutionContext` / `ValidatedTurnContext`**
   - ya son casi genéricos, pero nombres/errores incluyen semántica de negociación.
3. **State repository keys**
   - `negotiation_canonical` fijo: conviene parametrizar por flujo.
4. **Traces `nodes` shape**
   - hoy asume nodos memory/phase/planner/executor.

## 5) Riesgos si se copia demasiado literal

1. Duplicación de cientos de líneas de `flow_config.py`.
2. Drift entre runtime de `negociacion` y `conversacion_simple`.
3. Mayor coste de mantenimiento de superficies (IU/optimizador) por forks internos.
4. Tests casi duplicados difíciles de sostener.

## 6) Riesgos si se desacopla demasiado pronto

1. Refactor horizontal enorme sin entrega incremental.
2. Riesgo de romper contratos actuales de `negociacion`.
3. Complejidad de migración de trazas y tooling.

## 7) Respuesta a pregunta clave #1

### ¿Nuevo flujo real o variante/contexto de `negociacion`?

**Recomendación:** nuevo flujo real (`conversacion_simple`) con dos contextos oficiales.

**Razón:** la topología online de pipeline es una decisión de arquitectura de flujo (no de contenido contextual). Un contexto de `negociacion` no debería cambiar de 4 llamadas a 1 llamada si queremos mantener coherencia conceptual.

## 8) Respuesta a pregunta clave #2

### ¿Qué abstraer para “idéntico por fuera” y 1-LLM por dentro?

1. Capa de `flow runtime adapter` para que superficies llamen igual y el runtime concreto cambie internamente.
2. `entry_contract` con snapshot flow-agnostic + campos opcionales por topología.
3. Persistencia/trace con namespaces por `memory_key` configurable por flujo.
4. Resolución de contextos por flow root (`negociacion` y `conversacion_simple`).

## 9) Respuesta a pregunta clave #3

### Mayores acoplamientos actuales a `negociacion`

1. Naming de estado (`negotiation_*`) en runtime/tests.
2. Modelos de nodo especializados (`PlannerOutput`, `ExecutorOutput`, etc.).
3. `flow_config.py` monolítico con lógica específica de los 4 nodos.
4. Expectativas de traces/tests sobre nodos concretos.
