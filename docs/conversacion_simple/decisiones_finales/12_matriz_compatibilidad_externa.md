# 12 · Matriz de compatibilidad externa (`negociacion` vs `conversacion_simple`)

> Objetivo: definir exactamente qué significa “igual por fuera”.

---

## 1) Base metodológica

### Hecho observado

Las superficies actuales (`interfaz_usuario`, `optimizador`, legacy) se apoyan en contratos comunes de sesión/contexto/turn y en `execute_turn_with_contract`.

### Inferencia

Si `conversacion_simple` preserva esos contratos, puede divergir internamente en topología de nodos sin romper interfaz externa.

### Decisión

Compatibilidad externa se define por:
1. shape de API,
2. semántica de sesión/lock/TTL/contexto,
3. envelope de trace/meta.

---

## 2) Matriz API/endpoints

| Elemento | Hoy en `negociacion` | Objetivo `conversacion_simple` | Igual / equivalente / distinto | Impacto | Decisión |
|---|---|---|---|---|---|
| Bootstrap IU | `POST /api/interfaz_usuario/sessions/bootstrap` con `user_id/session_id/context_id/public_slug` | Mismo endpoint y request/response envelope | **Igual** | Externo nulo | Mantener shape |
| Turn IU | `POST /api/interfaz_usuario/negociacion/turn` | Misma semántica de turn stateful; enrutado al flow según contexto/selección | **Equivalente** | Externo mínimo | Mantener response contract |
| Finalize IU | `POST /api/interfaz_usuario/sessions/finalize` | Igual | **Igual** | Nulo | Mantener |
| New conversation IU | `POST /api/interfaz_usuario/negociacion/new_conversation` | Igual semántica | **Igual** | Nulo | Mantener |
| Bootstrap optimizador | `POST /api/optimizador/sessions/bootstrap` | Igual shape + flow/context aware internamente | **Equivalente** | Bajo | Mantener |
| Sandbox turn optimizador | `POST /api/optimizador/sandbox/turn` | Igual endpoint; cambia runtime interno | **Equivalente** | Bajo | Mantener |
| List contexts optimizador | `GET /api/optimizador/contexts` | Debe listar también `conversacion_simple` | **Distinto visible** | Medio | Extender payload |
| List prompts optimizador | `GET /api/optimizador/prompts` | Debe reflejar prompt único (`brain`) | **Distinto visible** | Bajo | Ajustar tooling |
| Legacy `/negociar` | endpoint deprecated con contexto explícito | Mantener para `negociacion`; no extender en V1 | **Igual** | Nulo | No tocar en V1 |

### Rutas de referencia

- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/optimizador/services.py`
- `backend/api/app.py`

---

## 3) Matriz sesión/estado operacional

| Elemento | Hoy en `negociacion` | Objetivo `conversacion_simple` | Igual / equivalente / distinto | No romper bajo ningún concepto | Decisión |
|---|---|---|---|---|---|
| Session lifecycle | bootstrap/active/finalized TTL | igual | **Igual** | Sí | Reusar `sessions/lifecycle.py` |
| Locks | lock por sesión + retry timeout | igual | **Igual** | Sí | Reusar `sessions/session_lock.py` |
| Surface ownership | sesión ligada a una superficie | igual | **Igual** | Sí | Reusar `sessions/surface_scope.py` |
| Context binding | sesión ligada a contexto estable | igual semántica | **Igual** | Sí | Reproducir contrato de conflicto |
| Context precheck | coherencia sesión/config/prompts_dir | igual | **Igual** | Sí | Reusar patrón `turn_context_validator` |
| Finalización | TTL finalized + estado final | igual | **Igual** | Sí | Reusar |
| OpenAI conversation ids | `conversation_id_before/after` y `previous_response_id_*` | mantener campos y semántica | **Equivalente** | Sí | Mantener en trace/meta |

### Rutas de referencia

- `backend/sessions/lifecycle.py`
- `backend/sessions/session_lock.py`
- `backend/sessions/surface_scope.py`
- `backend/negociacion/contexts/session_binding.py`
- `backend/negociacion/orchestration/turn_context_validator.py`
- `backend/negociacion/orchestration/turn_contract.py`

---

## 4) Matriz trace/observabilidad

| Elemento | Hoy en `negociacion` | Objetivo `conversacion_simple` | Igual / equivalente / distinto | Impacto | Decisión |
|---|---|---|---|---|---|
| Envelope trace | metadatos de turno/sesión/modelos/timings | mismo envelope | **Equivalente** | Bajo | Mantener campos troncales |
| `entry_contract` | se inyecta en último trace | igual | **Igual** | Nulo | Mantener |
| `context_meta` | generado por `build_trace_context_meta` | igual | **Igual** | Nulo | Mantener |
| conversation ids before/after | presentes en trace/meta | iguales | **Igual** | Nulo | Mantener |
| Stage timings | mapa de tiempos por etapa | igual estructura, distintas etapas internas | **Equivalente** | Bajo | Mantener clave `stage_timings_ms` |
| Shape de nodos | `memory/phase/planner/executor` | `brain` (+ opcional `maintenance`) | **Distinto interno** | Medio tooling | Adaptar lectores sin romper envelope |
| Guardrails | input/output decisions y flags | igual semántica | **Igual** | Nulo | Mantener |
| Error categories | `turn_execution_failed`, categorías retryable | igual taxonomía donde aplique | **Equivalente** | Bajo | Reusar categorías |
| Tooling optimizador/forensics | asume estructura actual en algunos puntos | debe aceptar ambos flows | **Distinto interno** | Medio | extender lectura por flow |

### Rutas de referencia

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/orchestration/turn_contract.py`
- `backend/negociacion/traces/*`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/negociacion/optimizador/services.py`

---

## 5) Invariantes externas obligatorias

1. APIs públicas de sesión/turn/finalize no deben romper shape esperado por clientes actuales.
2. Semántica de contexto stateful (binding + conflicto + precheck) debe mantenerse.
3. Locking/TTL/surface ownership deben conservar comportamiento.
4. `entry_contract` y `context_meta` deben seguir apareciendo en trace.
5. Guardrails deben mantener señalización observable (decision/reasons/rewrite flags).

---

## 6) Divergencias internas aceptables

1. Topología de nodos (4 → 1).
2. Contrato interno de output del runtime (p.ej. `BrainOutput`).
3. Estructura interna de estado específica del flow.
4. Tiempos por etapa internos mientras se conserve envelope y lectura básica.

---

## 7) Riesgos de falsa compatibilidad

1. **Parecer igual en API pero romper optimizador** por cambios en `nodes` trace.
2. **Parecer igual en sesión pero divergir en context precheck** si se relaja validación.
3. **Parecer igual en output textual** pero perder metadatos contractuales necesarios para debugging.
4. **Parecer igual en bootstrap** pero devolver `presentation_config` inconsistente por flow/context resolver incorrecto.

### Mitigación

- tests de compatibilidad externa por matriz,
- tests de tooling sobre traces mixtas (`negociacion` y `conversacion_simple`),
- checklist de invariantes obligatorias en PR de implementación.
