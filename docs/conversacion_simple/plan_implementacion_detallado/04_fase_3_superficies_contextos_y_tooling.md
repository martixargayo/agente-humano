# 04 · Fase 3 — Superficies, contextos oficiales y tooling

## 1) Alcance

Integrar `conversacion_simple` en superficies existentes (`interfaz_usuario`, `optimizador`) y activar contextos iniciales, manteniendo invariantes externas.

---

## 2) Qué se hará

1. Añadir selección flow-aware en bootstrap/turn según contexto.
2. Enlazar runtime `conversacion_simple` en IU y optimizador.
3. Activar contextos oficiales:
   - `baseline`
   - `negociacion_sala_reuniones`
4. Integrar presentation config contextual de nuevo flow.
5. Adaptar trace readers/comparadores del optimizador para soportar single-node traces.

---

## 3) Archivos existentes a modificar (propuestos)

## Interfaz usuario

- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/models.py` *(solo si hace falta exponer `flow_id`)*
- `backend/interfaz_usuario/presentation_resolver.py` *(si se vuelve multi-flow aware)*

## API app / serving

- `backend/api/app.py` *(si hay nuevas rutas públicas por slug de conversacion_simple, opcional)*

## Optimizador

- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/negociacion/optimizador/context_bridge.py`

## Contratos compartidos

- `backend/negociacion/services/context_http.py` *(si se reusa para nuevo namespace de errores)

---

## 4) Archivos nuevos a crear (propuestos)

- `backend/conversacion_simple/services/session_service.py`
- `backend/conversacion_simple/services/turn_service.py`
- `backend/conversacion_simple/services/legacy_service.py` *(solo si se decide endpoint legacy nuevo, probablemente NO en V1)*
- `backend/conversacion_simple/presentation/*` *(solo si se separa resolver propio; alternativa: reutilizar resolver IU flow-aware)

---

## 5) Endpoints/servicios: plan concreto

## 5.1 `interfaz_usuario`

### Propuesta operativa

- Mantener endpoints actuales de sesión.
- Hacer routing interno por flow/context:
  - si contexto pertenece a `negociacion` -> runtime actual
  - si contexto pertenece a `conversacion_simple` -> runtime nuevo

### Qué no se hará

- No crear endpoints paralelos “/conversacion_simple/...” en V1 si no son necesarios.

## 5.2 `optimizador`

### Propuesta operativa

- Mantener endpoint `/api/optimizador/sandbox/turn`.
- Resolver flow desde sesión/contexto sandbox.
- Ajustar `compare_turns` y `list_prompts` para flujos con topología distinta.

### Qué no se hará

- No romper payloads existentes salvo extensiones backward-compatible.

## 5.3 Legacy

- Mantener `/negociar` acotado a `negociacion` en V1.

---

## 6) Contextos y presentation

1. Publicar manifests/context assets de ambos contextos iniciales.
2. Garantizar equivalencia contractual entre ambos (tests espejo).
3. Resolver presentation de forma flow-aware sin alterar contrato de bootstrap.

---

## 7) Tabla explícita de compatibilidad

## Debe quedar exactamente igual

1. Semántica de bootstrap/finalize/new conversation.
2. Session lock + TTL + ownership.
3. Context contract stateful (binding/conflict/precheck).
4. Presence de `entry_contract` y `context_meta` en trace.

## Puede cambiar internamente

1. Topología de nodos de trace (`brain` en lugar de 4 nodos).
2. Estado canónico interno del flow.
3. Prompt list del optimizador por flow.

## Requiere extender payload/tooling

1. `list_contexts` optimizador para incluir flow.
2. `trace_reader` y `compare_turns` para mixed topology.
3. Posible campo `flow_id` en metadatos de respuestas (si mejora depuración).

---

## 8) Riesgos de falsa compatibilidad (fase)

1. Endpoint responde 200 pero tooling rompe al leer nodos.
2. Bootstrap parece correcto pero context resolver mezcla flujos.
3. Misma respuesta textual, distinto comportamiento de metadata contractual.

### Mitigación

- tests de contrato externo por endpoint,
- tests de tooling sobre trazas de ambos flows,
- checklist de invariantes externas antes de merge.

---

## 9) Tests de Fase 3

## IU

- bootstrap/turn/finalize con contexto `conversacion_simple`.
- conflicto de contexto/superficie consistente con contratos actuales.

## Optimizador

- sandbox turn flow-aware,
- list_contexts/list_prompts mixed-flow,
- compare_turns entre turnos del mismo flow y cross-flow (error controlado).

## Contextos

- equivalencia de `baseline` y `negociacion_sala_reuniones`.
- serving de presentation assets por contexto.

## Compatibilidad

- tests de invariantes externas obligatorias de matriz 12.

---

## 10) Qué queda fuera de Fase 3

- infraestructura completa de compresión diferida,
- tuning de resumen en conversaciones largas,
- optimizaciones avanzadas de observabilidad de memoria.

---

## 11) Criterio de Done de Fase 3

- IU y optimizador operan con `conversacion_simple` sin romper contratos externos.
- Contextos iniciales funcionan y son equivalentes por tests.
- Tooling base de traces soporta single-node.
- No regresiones en rutas de `negociacion`.
