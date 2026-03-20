# Diagnóstico fallo de carga en Railway con Redis

> Estado del repo tras este diagnóstico: se aplicó una mitigación inicial para que el cliente Redis del session store configure timeouts explícitos y haga `ping()` al inicializarse. Eso reduce los cuelgues silenciosos y hace fallar antes si Railway/Redis no responde.

## 1. Resumen ejecutivo

**Veredicto corto:** la causa más probable está en la combinación de **código de fase 3 + ausencia de timeouts/observabilidad** más que en un error evidente de la URL de Railway.

La URL privada que estás usando **cuadra** con Railway private networking. Lo que no cuadra bien es que el cliente Redis se construye sin `socket_connect_timeout`, sin `socket_timeout`, sin `health_check_interval`, sin `ping()` de validación y sin logs alrededor de la primera operación real. Eso deja este patrón:

1. el backend arranca “bien”;
2. `app.js` se sirve con 200;
3. el frontend hace bootstrap automático;
4. la primera operación real contra Redis ocurre en `get()/get_or_create()/save()`;
5. si Redis no responde, DNS privada falla o la conexión se queda esperando, el request inicial se queda colgado y la UI parece quedarse “cargando”.

Mi lectura técnica es que el síntoma encaja **mucho mejor** con un problema de primer acceso Redis que con un bug de serialización del snapshot o con un fallo de Railway puro.

## 2. Síntomas observados

- El frontend se sirve, al menos `GET /interfaz_usuario/app.js` devuelve `200 OK`.
- El escenario tarda muchísimo en cargar o no termina de cargar.
- No hay evidencia equivalente de que el bootstrap `/api/interfaz_usuario/sessions/bootstrap` complete correctamente.

Eso sugiere que el problema no está en servir assets estáticos, sino en el bootstrap runtime que depende ya del store de sesión.

## 3. Información de Railway analizada

### Variables backend
- `SESSION_STORE_BACKEND=redis`
- `REDIS_URL=redis://default:YAhbYLgKcUTmXetzczOFBadFTAucUSij@redis.railway.internal:6379`

### Variables Redis service
- `REDISHOST=${{RAILWAY_PRIVATE_DOMAIN}}`
- `REDISPORT=6379`
- `REDISUSER=default`
- `REDIS_PASSWORD=...`
- `REDIS_URL=redis://${{REDISUSER}}:${{REDIS_PASSWORD}}@${{REDISHOST}}:${{REDISPORT}}`

### Veredicto sobre la URL
La URL privada **sí me cuadra** para Railway private networking:
- usa hostname privado interno,
- usa puerto 6379,
- usa usuario/password válidos,
- no depende del endpoint público.

El warning de `REDIS_PUBLIC_URL` parece accesorio mientras el backend use `REDIS_URL` privado.

## 4. Revisión de código relevante

### `backend/api/app.py`
La app llama a `configure_session_store_from_env()` al importar el módulo. Pero eso **solo construye** el cliente; no valida conectividad. El cliente Redis queda creado antes del primer request, pero la conexión real se produce después, de forma lazy.

### `backend/sessions/state.py`
`configure_session_store_from_env()`:
- selecciona backend por env,
- si hay Redis, crea `RedisSessionStore(build_redis_client_from_url(redis_url))`,
- no hace `ping()`,
- no loguea backend seleccionado,
- no valida respuesta del servidor Redis,
- no configura timeouts.

### `backend/sessions/redis_store.py`
`build_redis_client_from_url()` usa `Redis.from_url(redis_url, decode_responses=False)` sin:
- `socket_connect_timeout`,
- `socket_timeout`,
- `health_check_interval`,
- `retry_on_timeout`,
- `ping()`.

Luego `RedisSessionStore.get()` llama a `client.get(...)` y `get_or_create()` hace `get()` seguido de `save()`.

Esto es especialmente importante porque el primer bootstrap de una sesión nueva dispara justo ese camino.

### `backend/interfaz_usuario/services.py`
`ensure_session()` llama a `get_session_state()` al principio. Eso significa que **el bootstrap inicial del escenario depende ya del store activo**. Si el store Redis cuelga, la carga inicial entera se queda bloqueada.

### `backend/interfaz_usuario_app/app.js`
El frontend hace bootstrap automático al cargar (`initInterfazUsuarioSession`). Si la request no termina, la UI se queda esperando. Hay `catch`, pero solo si la petición falla; si la conexión queda colgada a nivel socket/TCP, el navegador puede tardar mucho en soltar error.

## 5. Hipótesis consideradas

### A. Problema de Railway / Redis / networking
**Posible, pero no mi primera apuesta.**
Si la red privada no resolviera o Redis no contestara, el código actual lo convertiría en cuelgue aparente porque no hay timeouts ni validación eager.

### B. Problema de configuración de variables
**Menos probable.**
La URL privada parece bien formada y coherente con Railway.

### C. Problema de implementación en fase 3
**Muy probable.**
No porque el diseño del store sea conceptualmente incorrecto, sino porque el cliente Redis se usa con defaults demasiado permisivos y sin observabilidad.

### D. Problema del bootstrap inicial
**Muy probable.**
Es donde se usa Redis por primera vez y donde el síntoma encaja mejor.

### E. Problema del frontend esperando una respuesta que no llega
**Sí, pero como efecto secundario.**
No parece la causa raíz; parece la consecuencia de un backend/request colgado.

### F. Bloqueo/timeout por cómo se construye el cliente Redis
**Muy probable.**
De hecho es mi hipótesis principal.

### G. La primera request se queda colgada en `get/get_or_create/save`
**Muy probable.**
Es exactamente el camino que ejecuta el bootstrap de una sesión nueva.

## 6. Causa más probable

### Causa principal que considero más probable
**La implementación actual del cliente Redis en fase 3 no configura timeouts ni validación temprana, así que cualquier problema de conectividad privada o respuesta lenta se manifiesta como un cuelgue del primer bootstrap.**

### Evidencia que me lleva a esto
1. `Redis.from_url(...)` se construye sin timeouts.
2. La conexión es lazy: el deploy puede parecer sano aunque Redis no sea alcanzable realmente.
3. El primer bootstrap depende de `get_session_state()` → `RedisSessionStore.get_or_create()`.
4. No hay `ping()` en startup.
5. No hay logs alrededor de `get/get_or_create/save`.
6. El frontend auto-bootstrappea al cargar, así que el usuario percibe el problema como “el escenario no carga”.

## 7. Causas secundarias plausibles

### 7.1 Redis privado no accesible desde el backend
Puede pasar por networking interno, DNS privada o estado del servicio. Pero el problema seguiría viéndose agravado por la ausencia de timeouts.

### 7.2 DNS privada o handshake lento
Si `redis.railway.internal` tarda en resolver o abrir socket, el cliente actual puede esperar demasiado.

### 7.3 Error visible solo en la primera operación
Como la app no hace `ping()` en startup, no descubres el fallo hasta el primer `GET/SET` real.

### 7.4 Menos probable: bug de serialización/hidratación
No es mi hipótesis principal para este síntoma concreto, porque en una sesión nueva el primer problema suele ocurrir antes: al intentar leer/escribir en Redis. Un bug de envelope tendería a dar excepción más clara, no un “cargando infinito”.

## 8. Pruebas de diagnóstico recomendadas

## Prueba 1. Confirmar si el problema desaparece con memoria
Poner temporalmente:
- `SESSION_STORE_BACKEND=memory`

Si el escenario carga normal, la causa queda fuertemente acotada al path Redis.

## Prueba 2. Añadir `ping()` con log en startup
Al arrancar con backend Redis:
- crear cliente,
- loguear `session_store_backend=redis redis_url_host=...`,
- ejecutar `ping()` con timeout corto,
- si falla, log claro y error explícito.

Esto te dice si el problema es accesibilidad real a Redis antes de esperar al primer bootstrap.

## Prueba 3. Timeouts cortos en el cliente
Forzar al menos:
- `socket_connect_timeout=1` o `2`,
- `socket_timeout=1` o `2`,
- `health_check_interval=30`,
- opcionalmente `retry_on_timeout=False`.

Si el escenario deja de “colgarse” y pasa a fallar rápido con error explícito, ya confirmaste el diagnóstico.

## Prueba 4. Logs alrededor de bootstrap/session store
Añadir logs en:
- `configure_session_store_from_env()`
- `RedisSessionStore.get()`
- `RedisSessionStore.get_or_create()`
- `RedisSessionStore.save()`
- inicio y fin de `interfaz_usuario.services.ensure_session()`

Así ves si el request entra y en qué punto exacto se queda.

## Prueba 5. Forzar una ruta mínima de test Redis
Crear temporalmente un endpoint interno tipo:
- `GET /debug/session-store-ping`

Que haga:
- `configure_session_store_from_env(force=True)` o use el store activo,
- si es Redis, haga `PING`, `SET`, `GET`, `DELETE`.

Sirve para aislar Railway/Redis del resto del runtime de negociación.

## 9. Cambios mínimos recomendados

### Cambio mínimo 1. Timeouts explícitos al cliente Redis
En `build_redis_client_from_url()`:
- `socket_connect_timeout=2`
- `socket_timeout=2`
- `health_check_interval=30`

Este es el cambio mínimo más importante.

### Cambio mínimo 2. `ping()` controlado al configurar Redis
No hace falta volverlo bloqueante infinito. Basta con:
- si backend=redis, hacer `ping()` y loguear éxito/fallo;
- si falla, que quede clarísimo en logs.

### Cambio mínimo 3. Logging estructurado alrededor del store
Muy poca instrumentación ya te diría si el cuelgue ocurre en:
- selección del store,
- primera lectura,
- primera escritura,
- serialización,
- bootstrap público.

### Cambio mínimo 4. Mejor visibilidad del fallo en el frontend
No como fix raíz, pero sí como mitigación UX:
- timeout de bootstrap en cliente o mensaje más claro si tarda demasiado;
- hoy la UI depende de que el navegador decida cuándo considera fallida la request.

## 10. Conclusión honesta

### Lo que sí me cuadra
- la URL privada de Redis en Railway,
- que el deploy aparente estar bien,
- que `app.js` se sirva con 200,
- que el problema aparezca en la carga del escenario.

### Lo que no me cuadra bien del código actual
- ausencia total de timeouts en Redis,
- ausencia de `ping()` en startup,
- ausencia de logs en puntos críticos del primer acceso,
- lazy connection sin diagnóstico visible.

### Juicio final
Si me obligas a elegir una causa más probable entre Railway y el código, diría:

**más probable problema de implementación/diagnóstico en el código de fase 3 que problema puro de Railway**.

Más concretamente:
- Railway/private Redis puede estar bien,
- pero si hay cualquier microfallo de conectividad o latencia, el código actual lo convierte en “pantalla cargando” porque no falla rápido ni loguea bien.

## 11. Resumen súper detallado de evidencias

### `backend/sessions/redis_store.py`
- **Qué revisé:** construcción del cliente, operaciones `get/get_or_create/save`, formato de clave, `touch`.
- **Qué me cuadra:** el envelope se serializa de forma razonable; el roundtrip conceptual está bien.
- **Qué no me cuadra:** el cliente Redis se crea sin timeouts ni validación; eso es el mayor sospechoso del cuelgue.

### `backend/sessions/state.py`
- **Qué revisé:** `configure_session_store_from_env()`, contrato `SessionStore`, selección por env.
- **Qué me cuadra:** la selección `memory/redis/auto` es simple y correcta.
- **Qué no me cuadra:** no hay logs ni `ping()`; además el backend puede quedar “configurado” en Redis aunque la conectividad real no se haya probado todavía.

### `backend/api/app.py`
- **Qué revisé:** wiring del store al arrancar.
- **Qué me cuadra:** se configura el store una vez al inicio.
- **Qué no me cuadra:** como la conexión es lazy, el startup no garantiza realmente que Redis sea usable.

### `backend/interfaz_usuario/services.py`
- **Qué revisé:** camino de bootstrap y dependencia del store en `ensure_session()`.
- **Qué me cuadra:** el bootstrap es el sitio correcto para resolver sesión.
- **Qué no me cuadra:** el primer bootstrap depende totalmente de que Redis responda; si no, el escenario entero se bloquea desde el primer paso.

### `backend/interfaz_usuario_app/app.js`
- **Qué revisé:** bootstrap automático inicial y manejo de error.
- **Qué me cuadra:** la app consume bien la identidad devuelta por backend.
- **Qué no me cuadra:** si la request queda colgada, la UI no tiene timeout propio ni señal intermedia suficientemente diagnóstica.

### Config Railway
- **Qué revisé:** `SESSION_STORE_BACKEND`, `REDIS_URL`, host privado y warning de `REDIS_PUBLIC_URL`.
- **Qué me cuadra:** la URL privada parece correcta.
- **Qué no me cuadra:** nada grave en la URL; por eso no creo que el principal sospechoso sea la variable en sí.
