# Ejecución Fase 03 — fijación de contexto en sesión

## Resumen ejecutivo

La Fase 03 queda implementada de forma **conservadora y mínima**:

- la identidad contextual de la negociación se persiste en sesión;
- `ensure_session()` fija o reutiliza ese contexto;
- `create_new_conversation()` hereda el mismo contexto de la sesión base;
- `run_turn()` fuerza el backfill/reuso del contexto ligado a la sesión antes de ejecutar el turno;
- no cambia el baseline funcional efectivo, porque el único contexto oficial soportado sigue siendo `baseline_current` y el runtime continúa resolviendo el mismo baseline que ya usaba en Fase 02.

---

## Qué cambió exactamente

### Persistencia de contexto en sesión

Se añadió un binding mínimo y estable en `SessionState.world_state` bajo la clave:

- `world_state["negotiation_context"]`

Con este shape:

```json
{
  "flow_id": "negociacion",
  "context_id": "baseline_current",
  "context_version": "1.0.0"
}
```

No se rediseñó `SessionState` ni se alteró el shape táctico relevante de `CanonicalState`.

### Helpers nuevos de binding

Se creó `backend/negociacion/contexts/session_binding.py` para centralizar solo cuatro responsabilidades:

- leer contexto persistido de sesión;
- persistir contexto resuelto en sesión;
- hacer backfill conservador de sesiones legacy sin contexto;
- detectar conflicto explícito si alguien intenta rebootstrapear una sesión ya fijada con otro `context_id`.

---

## Dónde se persiste el contexto

La persistencia queda exactamente en:

- `SessionState.world_state["negotiation_context"]["flow_id"]`
- `SessionState.world_state["negotiation_context"]["context_id"]`
- `SessionState.world_state["negotiation_context"]["context_version"]`

Esto mantiene la identidad contextual a nivel sesión sin moverla al estado canónico del dominio.

---

## Bootstrap sin contexto

Si el cliente hace bootstrap sin `context_id`:

1. `ensure_session()` carga o crea la sesión;
2. si la sesión no tiene contexto persistido, se resuelve el baseline oficial por defecto;
3. ese baseline se persiste en `world_state["negotiation_context"]`;
4. la respuesta sigue siendo compatible con la superficie actual.

Resultado: los clientes actuales siguen funcionando exactamente como antes.

---

## Bootstrap con contexto explícito

`SessionBootstrapRequest` ahora acepta `context_id` opcional.

Si llega `context_id="baseline_current"`:

1. se resuelve ese contexto oficial;
2. se persiste en sesión;
3. la sesión queda fijada explícitamente a ese contexto.

Como todavía no existe un segundo contexto oficial, esto sigue siendo funcionalmente equivalente al baseline actual.

---

## Sesión ya existente

Si `ensure_session()` recibe una sesión ya existente:

- si la sesión ya tiene contexto persistido, **lo reutiliza**;
- si es una sesión legacy sin contexto persistido, hace **backfill al baseline**;
- si llega un `context_id` distinto del ya fijado, se aplica política conservadora de conflicto.

---

## Política conservadora elegida para conflictos

Se eligió **rechazar explícitamente** el intento de rebootstrap de una sesión existente con un `context_id` distinto.

### Comportamiento

Se lanza `HTTPException(status_code=409)` con detalle `session_context_conflict`.

### Por qué se eligió esta política

Porque es la forma más segura de cumplir el objetivo de la fase:

- evita mezcla silenciosa entre bootstrap y runtime;
- evita que una misma sesión cambie de identidad contextual a mitad de vida;
- evita esconder errores de integración del cliente;
- es más segura que ignorar silenciosamente el valor nuevo.

---

## Herencia en `new_conversation`

`create_new_conversation()` ahora:

1. lee o backfillea primero el contexto de la sesión base;
2. crea una nueva sesión vacía;
3. fija en la nueva sesión el **mismo** `context_id/context_version` heredado;
4. devuelve la nueva conversación sin caer accidentalmente al default por un camino distinto.

Con esto, abrir una nueva conversación no pierde la identidad contextual.

---

## Qué hace `run_turn()` ahora

`run_turn()` no introduce todavía selección context-aware completa del runtime, pero sí deja clara la dirección correcta:

- antes de ejecutar el turno, garantiza que la sesión tiene contexto fijado;
- si la sesión era legacy, la backfillea al baseline;
- si se dispara `new_conversation`, el turno corre sobre una sesión nueva que ya heredó el contexto correcto.

Esto evita que bootstrap y runtime queden desacoplados a nivel de identidad de sesión, aunque el runtime siga usando el único baseline oficial disponible.

---

## Por qué esto no cambia todavía el comportamiento funcional

No cambia el comportamiento funcional observable del baseline porque:

- el único `context_id` oficial soportado sigue siendo `baseline_current`;
- prompts efectivos no cambian;
- JSON efectivos no cambian;
- el pipeline y su orden no cambian;
- `finish_button_armed` no se toca;
- `CanonicalState` no se refactoriza ni cambia su shape relevante.

En otras palabras: se fija identidad contextual, pero todavía no se introduce un runtime multi-context completo.

---

## Qué sigue fuera de alcance hasta Fase 4

Sigue **fuera de alcance** en esta fase:

- URL pública por contexto;
- `public_slug` en superficie pública;
- frontend leyendo contexto desde URL;
- trazas completamente context-aware;
- evaluación context-aware;
- optimizer context-aware completo;
- segundo contexto oficial.

---

## Archivos tocados en esta fase

- `backend/negociacion/contexts/models.py`
- `backend/negociacion/contexts/session_binding.py`
- `backend/negociacion/contexts/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/tests/test_phase3_context_session_binding.py`
- `backend/scripts/check_phase3_context_session_binding.py`
- `docs/ejecucion_fase_03_fijacion_contexto_en_sesion.md`

---

## Validaciones implementadas

Se añadieron:

- test automatizado `backend/tests/test_phase3_context_session_binding.py`
- script manual `backend/scripts/check_phase3_context_session_binding.py`

Ambos cubren:

- baseline por defecto;
- contexto explícito baseline;
- reuso de contexto en sesión existente;
- conflicto de contexto sin mezcla silenciosa;
- herencia en `new_conversation`;
- persistencia exacta en `world_state`;
- backfill de sesiones legacy;
- preservación de la superficie baseline observable.
