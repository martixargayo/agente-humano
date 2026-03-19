# Fase 03 — fijación de contexto en sesión

## 1. Propósito exacto de la fase

Garantizar que sesión y runtime usan el **mismo contexto oficial** y evitar contaminación entre conversaciones/contextos.

Va después de la resolución de runtime porque primero hacía falta una identidad de contexto confiable para poder persistirla.

---

## 2. Qué se cambia exactamente

Se añaden metadatos de contexto a la sesión y a los caminos de creación/reinicio de conversación, sin romper la API actual.

### Objetivo técnico

Toda sesión de negociación debe poder responder:

- qué `context_id` usa;
- qué `context_version` usa;
- si viene de baseline o de un sandbox/clonado;
- y que cualquier nuevo turno reutilice exactamente ese contexto.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/sessions/state.py`
- `backend/negociacion/state/canonical_state.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/negociacion/pipeline.py` o capa de entrada equivalente si necesita aceptar contexto resuelto
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/session_bridge.py`
- `backend/negociacion/optimizador/models.py`

### Archivos nuevos posibles

- `backend/negociacion/contexts/session_binding.py` si se decide aislar helpers de fijación/lectura de contexto en sesión

---

## 4. Cambios exactos archivo por archivo

### `backend/sessions/state.py`

- **Responsabilidad hoy:** `SessionState` guarda `world_state`/history y es el contenedor persistente en RAM.
- **Cambio exacto:**
  - no rediseñar `SessionState` completo;
  - añadir solo una zona compatible para metadatos contextuales, preferiblemente dentro de `world_state` bajo clave estable, o en un campo nuevo estrictamente opcional si se considera más claro;
  - no romper sesiones antiguas que no tengan esos metadatos.
- **Compatibilidad:** backfill conservador al baseline actual cuando falte `context_id`.

### `backend/negociacion/state/canonical_state.py`

- **Responsabilidad hoy:** estado canónico del dominio sin identidad explícita de contexto.
- **Cambio exacto:**
  - decidir si `context_id/context_version` viven en `session` dentro del canonical state o solo en `world_state` fuera del canonical;
  - si se añaden al canonical, hacerlo de forma compatible y mínima;
  - si no se añaden al canonical, exponer helpers que sincronicen sesión <-> runtime correctamente.
- **Compatibilidad:** mantener shape observable del estado táctico igual; no introducir campos que cambien razonamiento del planner/executor.

### `backend/interfaz_usuario/models.py`

- **Responsabilidad hoy:** requests de bootstrap/turn sin `context_id`.
- **Cambio exacto:**
  - ampliar `SessionBootstrapRequest` con `context_id` opcional;
  - mantener defaults actuales para compatibilidad;
  - no hacer obligatorio `context_id` aún.
- **Compatibilidad:** clientes actuales siguen funcionando sin enviar contexto, resolviendo baseline por defecto.

### `backend/interfaz_usuario/services.py`

- **Responsabilidad hoy:** crear sesión, abrir nueva conversación y ejecutar turnos sin contexto explícito.
- **Cambio exacto:**
  - `ensure_session()` debe resolver y fijar `context_id` si no existe;
  - `create_new_conversation()` debe heredar `context_id/context_version` de la sesión base;
  - `run_turn()` debe cargar el contexto ya fijado en la sesión y no uno inferido ad hoc por cada turno.
- **Compatibilidad:** si el cliente no envía `context_id`, usar baseline.

### `backend/interfaz_usuario/__init__.py`

- **Responsabilidad hoy:** exponer endpoints bootstrap/new_conversation/turn.
- **Cambio exacto:** no cambiar rutas; solo dejar pasar `context_id` opcional si se amplía el modelo.
- **Compatibilidad:** total.

### `backend/negociacion/optimizador/models.py`

- **Responsabilidad hoy:** bootstrap y sandbox requests sin contexto oficial explícito.
- **Cambio exacto:** añadir `context_id` opcional en bootstrap/new conversation del optimizer y, si conviene, en sandbox turn metadata.
- **Compatibilidad:** defaults al baseline.

### `backend/negociacion/optimizador/services.py` y `session_bridge.py`

- **Responsabilidad hoy:** crear sandboxes y conversaciones nuevas copiando estado pero sin identidad contextual oficial.
- **Cambio exacto:** persistir `context_id/context_version` en metadata sandbox y heredarlo al clonar o crear new conversation.
- **Compatibilidad:** no cambiar todavía la lógica de overrides, solo fijar contexto base.

---

## 5. Estructura nueva que aparecería en esa fase

Posible helper nuevo:

```text
backend/
  negociacion/
    contexts/
      session_binding.py
```

Con helpers como:

- `bind_context_to_session(...)`
- `read_context_from_session(...)`
- `ensure_session_context(...)`
- `inherit_context_for_new_conversation(...)`

---

## 6. Qué NO se toca todavía

- URL pública final de contexto en frontend;
- trazas context-aware completas;
- evaluación context-aware;
- optimizer context-aware completo;
- estructura de `NegotiationPhase`;
- lógica de `finish_button_armed`.

---

## 7. Cómo se garantiza equivalencia funcional

- cuando no se pase `context_id`, se resuelve baseline por defecto;
- `new_conversation` hereda baseline, no cambia de caso;
- el bundle efectivo sigue siendo el mismo baseline;
- no cambian prompts efectivos;
- no cambian JSON efectivos;
- no cambia shape táctico del estado;
- no cambia la API actual porque `context_id` es opcional;
- no cambia evaluación visible;
- no cambia optimizer baseline más allá de persistir identidad contextual compatible.

---

## 8. Riesgos específicos de la fase

- fijar `context_id` en sesión pero no usarlo realmente en runtime;
- heredar mal el contexto en `new_conversation`;
- permitir bootstrap con un `context_id` y luego ejecutar turnos con otro por defecto;
- guardar contexto en dos sitios distintos sin prioridad clara.

---

## 9. Validaciones y checks recomendados

- crear sesión sin `context_id` y comprobar baseline por defecto;
- crear sesión con `context_id=baseline_current` y comprobar mismo resultado;
- abrir `new_conversation` y verificar herencia del contexto;
- comprobar que sesiones legacy sin `context_id` se backfillean a baseline sin errores.

---

## 10. Condición de salida

Toda sesión nueva de negociación queda ligada a un contexto oficial y el runtime reutiliza ese mismo contexto en todos los turnos.

---

## 11. Rollback / compatibilidad

Si algo falla, los endpoints pueden seguir aceptando payload antiguo y resolver baseline por defecto, manteniendo los metadatos contextuales como opcionales hasta estabilizar la fase.
