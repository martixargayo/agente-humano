# 03 · Diseño objetivo de `conversacion_simple`

## 1) Principio rector

`conversacion_simple` debe ser **externamente equivalente** a `negociacion` en contratos sistémicos (sesión/contexto/superficies/trazas), pero internamente debe ejecutar un **pipeline de una sola LLM online por turno**.

## 2) Componentes objetivo

1. **Context layer (`conversacion_simple.contexts`)**
   - resolver oficial, session binding, public mapping, prompt_io mapping.
2. **State layer (`conversacion_simple.state`)**
   - canonical state específico o variante compatible.
3. **Runtime layer (`conversacion_simple.orchestration`)**
   - `build_conversacion_simple_pipeline_config`
   - `run_conversacion_simple_turn`
4. **Surface adapters**
   - IU/optimizador/legacy (si aplica) enrutan al flujo según contexto/entrypoint.

## 3) Flujo E2E propuesto (texto-secuencia)

```text
[Surface API]
  -> acquire lock + touch TTL
  -> ensure session surface
  -> ensure session context (flow=conversacion_simple)
  -> build flow config (stateful)
  -> build turn context
  -> execute_turn_with_contract (mismo patrón)
      -> validate_turn_context_pre_execution
      -> run_conversacion_simple_turn
          -> input guardrails
          -> single llm call (brain node)
          -> output guardrails
          -> apply state update
          -> persist canonical + recent_dialogue + trace
  -> apply session TTL active
  -> return reply + meta + entry_contract
```

## 4) Lifecycle de sesión

Idéntico al de `negociacion`:

- bootstrap: crea/rehidrata + context bind + presentation config.
- turn: lock + ejecución + persistencia.
- finalize: marca status finalized con TTL corto.

## 5) Contratos

## 5.1 Turn contract

Mantener `execute_turn_with_contract` como wrapper estándar para todos los flujos stateful.

## 5.2 Context contract

Repetir las invariantes actuales:
- `effective_context_id` obligatorio en stateful,
- coherencia sesión/config/prompts_dir,
- errores tipados y traducibles a HTTP.

## 5.3 Trace contract

Mantener metadata principal:
- `context_meta`,
- `_entry_contract`,
- `conversation_id_before/after`,
- timings,
- guardrails.

Adaptar `nodes` a:
- `brain` (nodo único),
- opcionalmente `maintenance` (si hay compresión diferida ejecutada en ese turno, fuera del camino crítico).

## 6) Contextos iniciales

Crear:
- `conversacion_simple/contexts/baseline`
- `conversacion_simple/contexts/negociacion_sala_reuniones`

Ambos idénticos en contenido/contratos en esta fase.

## 7) Convivencia con `negociacion`

- `negociacion` sigue operando sin cambios funcionales.
- `conversacion_simple` entra en paralelo.
- Superficies seleccionan flujo por contexto o parámetro explícito de flujo (decisión abierta a validar).

## 8) Respuesta a pregunta clave #8

### ¿Qué puede quedarse tal cual y qué conviene desacoplar antes?

**Queda tal cual:** lifecycle, lock, context precheck, error bridge, presentation resolver, infra de store.

**Conviene desacoplar antes de implementar runtime nuevo:**
1. factorizar runtime monolítico de `flow_config.py` en piezas flow-agnostic,
2. separar modelos de trace por topología de nodos,
3. parametrizar `memory_key` y nombres de estado por flujo.
