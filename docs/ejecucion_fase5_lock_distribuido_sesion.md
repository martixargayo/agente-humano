# Ejecución fase 5 — lock distribuido por sesión

## 1. Resumen ejecutivo

Se implementó un **lock distribuido por sesión** con el mínimo cambio estructural necesario para proteger el path crítico sin reescribir el flujo negociador.

La solución:

- usa Redis cuando el backend ya está sobre `RedisSessionStore`;
- cae a lock en memoria cuando el store activo no expone cliente Redis;
- protege el turno crítico tanto en `interfaz_usuario` como en `optimizador`;
- devuelve `423 session_busy` cuando la sesión ya está ocupada;
- mantiene heartbeat/refresh del lock para turnos largos;
- libera el lock en `finally`, incluso si el turno falla.

## 2. Objetivo exacto de la fase 5

Evitar que dos requests concurrentes para la misma sesión:

- pisen `planner_state`;
- pisen `memory_working`;
- desordenen `recent_dialogue`;
- mezclen trazas;
- compitan sobre `conversation_id`;
- degraden continuidad táctica o contaminen el estado de sesión.

## 3. Veredicto técnico breve

El hueco más importante para multiusuario real **sí estaba abierto** antes de esta intervención.  
Ahora queda cubierto con un lock por clave de sesión (`user_id` + `session_id`) y con política fail-fast:

- el primer request entra;
- el segundo no espera indefinidamente;
- recibe una respuesta explícita de sesión ocupada;
- el lock se refresca mientras dura el turno;
- y se libera al terminar o al fallar.

## 4. Arquitectura antes y después

### Antes
- cada request podía entrar directamente al path de `run_turn()` / `run_sandbox_turn()`;
- no había exclusión mutua por sesión;
- si dos requests simultáneos tocaban el mismo `SessionState`, la corrección dependía de suerte temporal.

### Después
- antes de ejecutar el turno se adquiere un lock de sesión;
- la sección crítica queda serializada por sesión;
- la concurrencia entre sesiones distintas sigue permitida;
- el backend responde con error entendible cuando la sesión ya está ocupada.

## 5. Qué archivos toqué

- `backend/sessions/session_lock.py`
- `backend/sessions/redis_store.py`
- `backend/sessions/state.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/optimizador/services.py`
- `backend/tests/test_railway_multiuser_readiness.py`
- `backend/tests/test_phase4_phase5_session_runtime.py`

## 6. Qué cambié en cada archivo y por qué

### `backend/sessions/session_lock.py`
Archivo nuevo con la abstracción real del lock:

- `SessionBusyError`
- `InMemorySessionLockManager`
- `RedisSessionLockManager`
- helper `acquire_session_execution_lock()`

Se añadió aquí para no contaminar `state.py` ni `interfaz_usuario/services.py` con detalles Redis/Lua/heartbeat.

### `backend/sessions/redis_store.py`
- expuse `client` mediante propiedad de solo lectura;
- eso permite que el lock manager reutilice el mismo cliente Redis del store activo.

### `backend/sessions/state.py`
- pequeño endurecimiento relacionado con continuidad (fase 4), no con el lock en sí.

### `backend/interfaz_usuario/services.py`
- el turno público queda ahora envuelto en `acquire_session_execution_lock(...)`;
- si la sesión ya está ocupada, responde `HTTP 423` con payload `session_busy` y `Retry-After`.

### `backend/negociacion/optimizador/services.py`
- el sandbox del optimizador usa el mismo lock por sesión;
- esto evita que una sesión sea mutada a la vez desde dos superficies distintas.

### `backend/tests/test_railway_multiuser_readiness.py`
- se amplió el fake Redis para soportar las primitivas del lock (`set nx ex`, `eval`) además de las del store.

### `backend/tests/test_phase4_phase5_session_runtime.py`
- se añadió la batería principal de pruebas de concurrencia y continuidad.

## 7. Cómo funciona el lock distribuido

### Clave de lock
La clave Redis del lock es:

`session-lock:{user_id}:{session_id}`

### Adquisición
Se usa:

- `SET key token NX EX ttl`

Si el lock ya existe:

- no se bloquea el request;
- se levanta `SessionBusyError`;
- la API responde con `423`.

### Propiedad del lock
Cada adquisición genera un token único (`uuid4().hex`).  
Ese token:

- identifica al propietario actual del lock;
- permite refrescarlo y liberarlo solo si el request sigue siendo el dueño.

### Refresh / heartbeat
Mientras el turno está corriendo:

- un hilo ligero de heartbeat llama periódicamente a un script Redis equivalente a:
  - si `GET key == token`, entonces `EXPIRE key ttl`
  - si no, no refresca y registra pérdida de ownership.

### Liberación
Al salir del contexto:

- se detiene el heartbeat;
- se ejecuta un script Redis equivalente a:
  - si `GET key == token`, `DEL key`
  - si no, no toca el lock.

## 8. Claves Redis usadas

- **Store de sesión:** `session:{user_id}:{session_id}`
- **Lock de ejecución:** `session-lock:{user_id}:{session_id}`

No se reutiliza la misma key del snapshot; el lock vive separado para no mezclar payload operativo con coordinación runtime.

## 9. Política de timeout / expiración / refresh si aplica

### Variables de entorno
- `SESSION_EXECUTION_LOCK_TTL_SECONDS`  
  Default: `180`

- `SESSION_EXECUTION_LOCK_REFRESH_SECONDS`  
  Default: `30`

- `SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS`  
  Default: `2`

### Justificación
- `TTL=180s` da margen suficiente para turnos con latencia alta o nodos LLM lentos;
- `refresh=30s` evita que el lock expire a mitad de turno en escenarios normales;
- `retry_after=2s` da a la UI y a clientes una señal simple para reintentar sin colgarse.

## 10. Comportamiento cuando la sesión está ocupada

### En superficie pública y optimizador
Se devuelve:

- `HTTP 423`
- detalle:
  - `error: session_busy`
  - `user_id`
  - `session_id`
  - `retry_after_seconds`
  - `lock_backend`

### Motivo de esta decisión
No se hace wait/retry implícito en backend porque:

- puede dejar colgada la UI;
- puede producir colas invisibles;
- dificulta observar contención real;
- y puede introducir reentradas raras con retries del cliente o del navegador.

## 11. Riesgos evitados

Con este lock se evita directamente:

- doble mutación concurrente del mismo `SessionState`;
- carreras sobre `conversation_id`;
- trazas fuera de orden por sesión;
- contaminación de `recent_dialogue`;
- pisado de `planner_state`, `memory_working` y `negotiation_state`;
- mezcla entre `interfaz_usuario` y `optimizador` si ambos tocan la misma sesión a la vez.

## 12. Riesgos que siguen abiertos

- si el proceso muere justo después de adquirir lock, la liberación depende del TTL, no de un unlock limpio;
- si el turno durara mucho más que el TTL y además fallara repetidamente el heartbeat, podría perderse ownership;
- no hay todavía política de retry/backoff en frontend específica para `423`;
- el lock serializa la sesión completa, no subdominios más finos del estado (decisión deliberadamente conservadora).

## 13. Impacto esperado en el flujo de negociación

### Impacto positivo
- más consistencia de estado;
- menos riesgo de residuos;
- continuidad OpenAI más robusta en producción multiusuario;
- menos corrupción silenciosa.

### Coste asumido
- requests simultáneos sobre la misma sesión ya no “compiten”; uno entra y el otro falla rápido.

Ese tradeoff es correcto para este producto en la fase actual.

## 14. Impacto esperado sobre contaminación/residuos

El impacto es claramente positivo porque:

- reduce mezclas entre turnos;
- evita que dos planes o respuestas actualicen la misma sesión en paralelo;
- disminuye el riesgo de divergencia entre snapshot local y continuidad OpenAI.

## 15. Tests ejecutados

- `pytest backend/tests/test_phase4_phase5_session_runtime.py backend/tests/test_railway_multiuser_readiness.py backend/tests/test_phase3_context_session_binding.py`

## 16. Resultados de tests

Los tests añadidos/verificados cubren:

1. continuidad roundtrip del snapshot;
2. preservación de `conversation_id` en reentrada;
3. aislamiento entre sesiones;
4. nueva conversación con continuidad nueva;
5. rechazo de segundo acquire sobre misma sesión;
6. paralelismo correcto entre sesiones distintas;
7. `session_busy` en path público;
8. liberación del lock tras fallo;
9. no interferencia entre sesiones distintas;
10. coordinación cruzada entre `interfaz_usuario` y `optimizador`.

Todos pasaron.

## 17. Limitaciones

- El lock en memoria es solo fallback local; la garantía distribuida real depende de Redis.
- No se añadió una cola de ejecución por sesión; la estrategia es fail-fast.
- No se implementó aún una telemetría agregada de contención, solo logging puntual.
- No se cambiaron aún las reacciones UX del frontend ante `423`.

## 18. Conclusión final honesta

La fase 5 queda **resuelta de forma práctica, simple y realista** para el estado actual del producto.

No es una sobrearquitectura; es una protección conservadora del path crítico:

- suficiente para Railway + Redis;
- compatible con la continuidad OpenAI ya existente;
- y útil para producción multiusuario real sin reescribir el pipeline.

## 19. Resumen súper detallado de cambios

### `backend/sessions/session_lock.py`
- **Qué toqué:** archivo nuevo con lock manager en memoria + Redis y heartbeat.
- **Por qué:** centralizar coordinación por sesión sin invadir el resto del runtime.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí, directamente.
- **¿Prepara fases futuras?:** sí, deja base para métricas de contención, retries más finos o upgrade de estrategia.
- **¿Modifica algo existente o solo endurece?:** endurece el runtime y cierra un hueco estructural.

### `backend/sessions/redis_store.py`
- **Qué toqué:** propiedad `client`.
- **Por qué:** permitir reutilizar el cliente Redis del store activo.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** sí, de forma indirecta.
- **¿Prepara fases futuras?:** sí, facilita coordinación adicional sobre Redis si hiciera falta.
- **¿Modifica algo existente o solo endurece?:** endurece/instrumenta.

### `backend/interfaz_usuario/services.py`
- **Qué toqué:** envolví `run_turn()` en lock de sesión y mapeé colisión a `HTTP 423`.
- **Por qué:** proteger el path crítico público.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí, directamente.
- **¿Prepara fases futuras?:** sí, porque explicita el contrato de “sesión ocupada”.
- **¿Modifica algo existente o solo endurece?:** endurece sin cambiar el flujo negociador base.

### `backend/negociacion/optimizador/services.py`
- **Qué toqué:** mismo lock en sandbox turn del optimizador.
- **Por qué:** evitar carreras cross-surface sobre la misma sesión.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí, para sandbox/inspección.
- **¿Prepara fases futuras?:** sí, deja coordinación coherente entre superficies.
- **¿Modifica algo existente o solo endurece?:** endurece.

### `backend/tests/test_railway_multiuser_readiness.py`
- **Qué toqué:** amplié el fake Redis.
- **Por qué:** soportar primitivas del lock además de primitivas del store.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** no.
- **¿Prepara fases futuras?:** sí, simplifica más pruebas Redis-like.
- **¿Modifica algo existente o solo endurece?:** endurece validación.

### `backend/tests/test_phase4_phase5_session_runtime.py`
- **Qué toqué:** batería principal de pruebas de fase 4 y 5.
- **Por qué:** aportar evidencia ejecutable y prevenir regresiones.
- **Tamaño del cambio:** grande.
- **¿Afecta al runtime crítico?:** no directamente; sí a la seguridad de evolución del runtime crítico.
- **¿Prepara fases futuras?:** sí, sirve de red de seguridad para siguientes fases.
- **¿Modifica algo existente o solo endurece?:** endurece validación.
