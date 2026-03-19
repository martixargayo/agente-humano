# Ejecución Fase 07 — optimizer context-aware

## 1. Qué se cambió exactamente

Se remata la Fase 7 para que el optimizer quede apoyado explícitamente sobre un **contexto oficial base** y no sobre un baseline implícito ambiguo.

El cierre fino de la fase deja estas garantías:

- el optimizer fija `baseline_current` como contexto oficial por defecto;
- `context_id="baseline_current"` funciona también de forma explícita;
- clone sandbox y new conversation heredan el contexto oficial de la sesión origen;
- si se intenta pedir un contexto distinto al ya ligado a la sesión origen, se rechaza con conflicto explícito;
- los overrides del optimizer siguen existiendo, pero viven **encima** de `base_context` y no lo sustituyen.

## 2. Archivos tocados en este cierre

- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/optimizador/context_bridge.py`
- `backend/negociacion/optimizador/models.py`
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/session_bridge.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/tests/test_phase7_optimizer_context_aware.py`
- `backend/scripts/check_phase7_optimizer_context_aware.py`

## 3. Cómo queda ahora el optimizer respecto al contexto oficial

El optimizer ya no opera solo sobre un bundle baseline implícito. Ahora opera así:

- **contexto oficial base** (`base_context`)
- + **sesión sandbox**
- + **overrides experimentales opcionales**

Esto significa que cada sesión optimizer relevante puede declarar qué contexto oficial está simulando, aunque luego tenga overrides de prompt/config/contextual por encima.

## 4. Dónde vive y cómo se persiste `base_context`

`base_context` queda visible en tres niveles diagnósticos:

1. **Sesión optimizer bootstrap**
   - respuesta de bootstrap con `base_context`
   - `world_state["negotiation_context"]` como binding oficial persistido

2. **Metadatos de sandbox**
   - `world_state["optimizador_sandbox_meta"]["base_context"]`
   - visible también en la respuesta de clone/new conversation

3. **Metadata de turno optimizer**
   - `trace["_optimizador"]["base_context"]`
   - conserva `context_id`, `context_version` y `context_scope`

## 5. Herencia en clone y new conversation

La política implementada es conservadora:

- si la sesión origen ya está ligada a `baseline_current`, la sandbox hereda exactamente ese contexto;
- new conversation hereda exactamente el contexto oficial ya ligado a la sesión base;
- no se vuelve a resolver “por otro lado” de forma silenciosa;
- no se permite pedir un `context_id` distinto al ya ligado en origen.

## 6. Política de conflicto elegida

La política es explícita y segura:

- si se intenta clone/new conversation con un `context_id` distinto al de la sesión origen,
- se devuelve error estable `optimizer_context_conflict`,
- y no se hace mezcla silenciosa de contexto.

Esto mantiene la misma filosofía conservadora ya aplicada en las fases 3 y 4.

## 7. Qué NO se tocó todavía

Para cerrar Fase 7 **no** se tocó:

- motor conversacional;
- lógica de negociación;
- runtime público;
- evaluación;
- prompts baseline;
- frontend del optimizer;
- segundo contexto oficial;
- expansión multi-context real.

## 8. Por qué esto cierra Fase 7

Con este remate ya quedan cubiertos los requisitos de salida de la fase:

- el optimizer declara y persiste un `base_context` oficial;
- clone y new conversation heredan ese contexto correctamente;
- `run_sandbox_turn()` mantiene visible el contexto oficial base;
- los overrides coexisten por encima del contexto oficial y no lo ocultan;
- el `trace_reader` puede resumir el contexto del optimizer de forma diagnóstica;
- existen tests y un script manual específicos de Fase 7.

## 9. Qué queda explícitamente fuera de alcance para Fase 8

Este cierre **no** introduce todavía:

- múltiples contextos oficiales activos;
- selección avanzada de contextos desde UI;
- rediseño del optimizer;
- reinterpretación de datasets/evals por contexto múltiple;
- cambios estructurales en prompts o en el pipeline negociador.

La siguiente fase, si existe, deberá construir sobre esta base ya explícita y observable, no rehacerla.
