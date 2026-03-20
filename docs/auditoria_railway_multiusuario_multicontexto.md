# Auditoría Railway multiusuario + multicontexto

## 1. Resumen ejecutivo

El repositorio **no está listo** para asumir con seguridad un despliegue Railway multiusuario, multicontexto y con posibles múltiples réplicas si el tráfico real depende de continuidad conversacional, optimizer state o evaluación asíncrona. La causa principal no es un fallo aislado sino un patrón arquitectónico repetido: piezas clave del sistema viven en memoria del proceso (`SESSIONS`, repositorio de evaluación en memoria, overrides del optimizer en `_OVERRIDE_STORE`) y se exponen mediante endpoints sin aislamiento de tenant/owner.

Lo positivo es que sí existe una intención clara de separar superficies y contextos:
- binding explícito de contexto por sesión,
- conflicto 409 si se intenta reutilizar una misma sesión para otra superficie,
- propagación de `context_meta` en trazas,
- separación semántica entre `interfaz_usuario` y `optimizador`.

Pero esa base convive con supuestos frágiles de single-process:
- continuidad basada en RAM local,
- bootstrap público con identidad por defecto compartida,
- listados globales del optimizer,
- evaluación asíncrona dependiente del mismo proceso que aceptó el job,
- overrides y sandboxes no persistidos.

## 2. Veredicto corto

**Veredicto honesto:** la arquitectura actual es válida para desarrollo, demos controladas y auditorías locales, pero **todavía depende de memoria local y de una única réplica** para la continuidad real del producto. Si mañana se activa Railway con varios usuarios simultáneos y varias réplicas, la probabilidad de roturas o contaminación operacional es alta, especialmente en:
- continuidad conversacional,
- jobs de evaluación,
- overrides del optimizer,
- sesiones públicas con IDs por defecto.

## 3. Arquitectura actual observada

### Runtime conversacional
- El estado base de sesión se resuelve con `get_session_state(user_id, session_id)` y se almacena en un diccionario global `SESSIONS`.
- El runtime de negociación persiste dentro de `state.world_state`:
  - `negotiation_canonical`,
  - `negotiation_canonical_recent_dialogue`,
  - `negotiation_canonical_traces`,
  - binding de contexto,
  - binding de superficie.
- El pipeline guarda canónico, recent dialogue y trazas en el propio `SessionState`, y luego vuelve a grabar ese mismo objeto en `SESSIONS`.

### Interfaz pública
- `interfaz_usuario` bootstrappea sesión con `user_id`/`session_id` que llegan del cliente.
- Si no llegan, el modelo usa por defecto `u_interfaz` + `interfaz-main`.
- El frontend público también renderiza esos mismos valores por defecto en HTML.

### Optimizer
- Usa las mismas `SESSIONS` que el runtime principal.
- El estado de overrides vive en `_OVERRIDE_STORE`, un diccionario global por `optimizer_session_id`.
- Los prompt bundles experimentales se materializan en `TemporaryDirectory`, o sea disco local efímero del contenedor.
- Los clones/new conversation de sandbox se crean duplicando el `SessionState` en RAM.

### Evaluación
- Usa `ThreadPoolExecutor` local al proceso.
- El repositorio de jobs/reports es `InMemoryFeedbackRepository`.
- El worker lee el `SessionState` de `SESSIONS`, construye el bundle y persiste resultado solo en ese repositorio en memoria.

## 4. Qué partes son seguras

Estas piezas sí muestran una dirección correcta:

1. **Binding explícito de contexto por sesión.**
   Una vez fijado el contexto, un intento de reusar la sesión con otro `context_id` devuelve conflicto. Esto reduce mezcla accidental entre contextos en una misma clave de sesión.

2. **Binding explícito de superficie.**
   `interfaz_usuario` y `optimizador` no pueden apropiarse silenciosamente de la misma tupla `(user_id, session_id)`; si se reusa la misma clave con otra superficie, hay 409.

3. **Context provenance en trazas.**
   Las trazas incluyen `context_meta` y el `entry_contract` añade superficie, entrypoint y snapshot de configuración. Para depuración forense esto está bien orientado.

4. **Separación lógica de conversaciones nuevas.**
   `create_new_conversation` y `new_conversation_session` generan un `session_id` nuevo, no simplemente un reset parcial del mismo bucket.

5. **Locks parciales en algunos componentes.**
   El repositorio de evaluación en memoria usa `Lock`; la sesión resumidora usa `asyncio.Lock`. Esto ayuda intra-proceso, aunque no resuelve multi-réplica ni durabilidad.

## 5. Qué partes dependen de RAM / proceso

### 5.1 Sesiones runtime
Toda la continuidad conversacional depende de:
- `SESSIONS: Dict[SessionKey, SessionState] = {}`.

Eso implica que viven solo en RAM del proceso:
- `history`,
- `world_state`,
- `negotiation_canonical`,
- `planner_state`,
- `memory_working`,
- `negotiation_state`,
- `openai_thread.conversation_id`,
- `openai_thread.previous_response_id`,
- `recent_dialogue`,
- `traces`,
- binding de contexto,
- binding de superficie.

Si el contenedor reinicia, todo eso desaparece.

### 5.2 Evaluación
`REPOSITORY = InMemoryFeedbackRepository()` implica que viven solo en RAM del proceso:
- jobs,
- estados (`created`, `queued`, `running_*`, `completed`, `failed`),
- reports,
- artifacts,
- stage latencies.

Un reinicio del contenedor o un request posterior servido por otra réplica rompe polling y recuperación de resultados.

### 5.3 Optimizer
`_OVERRIDE_STORE` depende de la RAM local. Se pierden al reiniciar:
- modo mirror/sandbox,
- entries pendientes,
- committed entries,
- workspace_version.

Además los prompt bundles temporales se montan con `TemporaryDirectory`, por lo que no son compartibles entre réplicas y dependen de filesystem efímero.

### 5.4 Jobs y workers locales
La evaluación se lanza con `ThreadPoolExecutor(max_workers=4)` dentro del mismo proceso web. No hay cola externa ni coordinación distribuida.

## 6. Riesgos bajo Railway

### 6.1 Reinicios del contenedor
**Riesgo alto.** Railway puede reiniciar por deploy, health issue, OOM o reprogramación. Al reiniciar se pierde:
- continuidad conversacional,
- hilos OpenAI,
- trazas del runtime en curso,
- sandboxes del optimizer,
- jobs/reports de evaluación.

### 6.2 Múltiples réplicas
**Riesgo muy alto.** Sin sticky sessions ni storage compartido:
- request A puede leer una sesión en réplica 1,
- request B puede caer en réplica 2 y ver la sesión vacía,
- polling de evaluación puede consultar una réplica distinta a la que ejecutó el job,
- overrides del optimizer pueden aparecer/desaparecer según la réplica.

### 6.3 Rolling deploy / zero downtime
**Riesgo alto.** Durante despliegues con varias versiones conviviendo, cualquier sesión viva en memoria de la réplica antigua se puede perder cuando el balanceador mande la siguiente request a la nueva.

### 6.4 Filesystem efímero
**Riesgo medio-alto.** El código usa `TemporaryDirectory` para bundles del optimizer. Sirve para ejecución local por request, pero no como persistencia ni como medio de coordinación entre nodos.

### 6.5 Healthchecks y warm instances
No se observa infraestructura externa para rehidratar estado tras un cold start. El sistema depende de que la misma instancia caliente conserve RAM previa.

## 7. Riesgos bajo multiusuario simultáneo

### 7.1 Identidad pública compartida por defecto
Este es uno de los problemas más graves. La interfaz pública define por defecto:
- `user_id = "u_interfaz"`
- `session_id = "interfaz-main"`

Y el HTML expone esos mismos valores por defecto. Si el frontend no los sobreescribe por usuario real, varios usuarios entrarán a la **misma sesión** y compartirán:
- canonical state,
- planner state,
- memory_working,
- traces,
- hilo OpenAI,
- recent dialogue.

### 7.2 Falta de aislamiento/ownership en endpoints del optimizer
El optimizer lista todas las sesiones globales y expone lectura por `(user_id, session_id)` sin autenticación ni control de owner. Eso significa que un usuario del optimizer puede ver sesiones de otros usuarios del optimizer si conoce o descubre las claves.

### 7.3 Objeto de sesión compartido sin lock por sesión
`get_session_state` devuelve el mismo objeto mutable `SessionState` a múltiples requests concurrentes. No existe lock por sesión al ejecutar turnos. Dos requests simultáneos sobre la misma sesión pueden:
- intercalar escrituras en `history`,
- competir sobre `openai_thread`,
- sobrescribir `planner_state`,
- dejar trazas en orden no determinista,
- producir continuidad incoherente.

## 8. Riesgos bajo multicontexto simultáneo

### 8.1 Lo que sí está bien
El binding de contexto reduce la mezcla silenciosa cuando una misma sesión intenta cambiar de contexto.

### 8.2 Lo que sigue siendo frágil
Aunque el contexto quede fijado, el bucket sigue siendo `SessionState` en RAM. Por tanto el aislamiento real depende de que:
- el `session_id` sea único,
- el frontend no reutilice IDs por error,
- no se pierda la sesión al caer en otra réplica.

### 8.3 Riesgo de baseline accidental en cold state
Si una request cae en una réplica que no conoce la sesión anterior, el sistema vuelve a crear una sesión vacía y puede terminar resolviendo contexto por defecto/baseline en lugar del contexto previamente fijado, salvo que el cliente vuelva a bootstrappear explícitamente con el contexto correcto.

### 8.4 Namespace del optimizer
Los overrides del optimizer se separan por `optimizer_session_id`, pero ese namespace también es local al proceso y no está vinculado de forma durable a un owner ni a una sesión persistente compartida.

## 9. Riesgos específicos de contaminación

### 9.1 Dentro de la misma sesión
El runtime canónico conserva en el mismo bucket:
- `planner_state`,
- `memory_working`,
- `negotiation_state`,
- `selected_memory`,
- `openai_thread`,
- `recent_dialogue`,
- `traces`.

Eso es correcto si la sesión es una unidad durable y exclusiva de un único usuario/flow. Pero hoy no siempre lo es, porque puede haber:
- reuse accidental de IDs por defecto,
- requests concurrentes sobre la misma sesión,
- recuperación vacía tras cambio de réplica.

### 9.2 Entre episodios / conversaciones reabiertas
El sistema usa nuevos `session_id` para nuevas conversaciones, lo cual es bueno. Pero cualquier reuso manual del mismo `session_id` reactiva el estado completo previo, incluyendo thread y planner state. No hay capa de TTL, versionado durable ni marca de “session tombstone” persistente.

### 9.3 Entre optimizer e interfaz_usuario
La separación de superficie mitiga contaminación cruzada directa. Aun así ambos viven sobre la misma infraestructura de `SESSIONS`, así que el problema de fondo sigue siendo la dependencia de RAM local.

### 9.4 Entre réplicas
Aquí la contaminación no es mezcla sino **inconsistencia**: una réplica ve residuos anteriores y otra ve vacío. En práctica, la calidad se degrada igual o peor porque la continuidad se vuelve no determinista.

## 10. Riesgos específicos del optimizer

1. **Bootstrap/list_sessions depende de `SESSIONS`.** No hay repositorio durable.
2. **Overrides globales en `_OVERRIDE_STORE`.** Se pierden en restart y no se comparten entre réplicas.
3. **Clone/new conversation solo en RAM.** Los sandboxes clonados desaparecen al reiniciar.
4. **Prompt bundles temporales en `TemporaryDirectory`.** Correcto para request-scoped temp files, no para persistencia.
5. **Aislamiento parcial pero sin seguridad multi-tenant.** El optimizer lista todas las sesiones globales y permite navegar por sesiones existentes sin ownership checks.
6. **Dependencia de la sesión base.** Si la sesión base desaparece por cambio de réplica, el sandbox/conversation provenance puede quedar huérfano.

## 11. Riesgos específicos de evaluación

1. **Jobs concurrentes solo locales.** `ThreadPoolExecutor(max_workers=4)` escala solo dentro de una réplica.
2. **Polling frágil.** El cliente puede preguntar estado a una réplica distinta y obtener 404.
3. **Resultados no durables.** Reportes desaparecen tras restart.
4. **Fuente de verdad dependiente de `SESSIONS`.** El bundle de evaluación se construye leyendo la sesión viva en RAM.
5. **Sin cola externa ni retries distribuidos.** Si el proceso muere, el job muere con él.

## 12. Experimentos ejecutados

Se añadieron pruebas y un script reproducible para validar estas hipótesis:

1. **Reinicio lógico de sesiones.**
   Se crea una sesión, se limpia `SESSIONS`, se verifica que el estado desaparece.

2. **Reinicio lógico de evaluación.**
   Se crea un job de evaluación, se limpia el repositorio in-memory, se verifica 404 posterior.

3. **Reinicio lógico del optimizer.**
   Se crean overrides, se limpia `_OVERRIDE_STORE`, se comprueba pérdida total.

4. **Identidad pública compartida.**
   Se bootstrappea dos veces la interfaz pública sin payload explícito y ambas caen en `u_interfaz / interfaz-main`.

5. **Listado global multiusuario del optimizer.**
   Se crean sesiones de dos usuarios y el endpoint global las devuelve a la vez.

6. **Concurrencia intra-sesión sin lock.**
   Dos threads obtienen el mismo objeto `SessionState` y escriben sobre él sin exclusión por sesión.

## 13. Evidencia encontrada

### Estado durable real por categoría

| Categoría | Ubicación actual | Durable | Riesgo Railway |
|---|---|---:|---|
| Sesiones runtime | `SESSIONS` en RAM | No | Alto |
| Canonical state | `state.world_state` dentro de `SessionState` | No | Alto |
| Recent dialogue | `world_state[<memory_key>_recent_dialogue]` | No | Alto |
| Traces runtime | `world_state[<memory_key>_traces]` | No | Alto |
| Binding de contexto | `world_state[negotiation_context]` | No | Alto |
| Binding de superficie | `world_state[_session_surface]` | No | Alto |
| OpenAI thread ids | `negotiation_canonical.openai_thread` | No | Alto |
| Jobs de evaluación | `InMemoryFeedbackRepository` | No | Alto |
| Reports evaluación | `InMemoryFeedbackRepository` | No | Alto |
| Overrides optimizer | `_OVERRIDE_STORE` | No | Alto |
| Sandboxes optimizer | clones en `SESSIONS` | No | Alto |
| Prompt bundles optimizer | `TemporaryDirectory` local | No | Medio |
| Context packs/prompts/assets | ficheros del repo | Sí (imagen del deploy) | Bajo |

### Dependencias claras de single instance
- continuidad de conversación,
- polling de evaluación,
- visibilidad de overrides del optimizer,
- reuso de sandbox sessions,
- conservación de `conversation_id` / `previous_response_id`.

## 14. Lista priorizada de problemas

### P0
1. **Identidad pública por defecto compartida (`u_interfaz` / `interfaz-main`).**
2. **Estado conversacional solo en `SESSIONS`.**
3. **Evaluación solo en memoria.**
4. **Overrides del optimizer solo en memoria.**

### P1
5. **Sin locking por sesión para turnos concurrentes.**
6. **Optimizer sin ownership/authz al listar y leer sesiones.**
7. **Continuidad dependiente de caer en la misma réplica.**

### P2
8. **Bundles temporales del optimizer en disco efímero.**
9. **Workers de evaluación embebidos en el proceso web.**
10. **Ausencia de strategy explícita de rehidratación/TTL/versionado de sesión.**

## 15. Fixes mínimos recomendados

1. **Eliminar inmediatamente IDs por defecto compartidos en interfaz pública.**
   Generar `user_id` y `session_id` únicos en cliente o, mejor, emitirlos desde backend al bootstrap.

2. **Persistir `SessionState` en un store externo durable.**
   Mínimo aceptable: Postgres o Redis persistente con serialización explícita del canónico, recent dialogue, traces y metadata de sesión.

3. **Persistir jobs/reportes de evaluación fuera del proceso.**
   Postgres es el mínimo razonable para estados; S3-compatible o storage persistente para artifacts grandes si aparecen.

4. **Persistir overrides/sandboxes del optimizer.**
   Al menos una tabla/document store keyed por `optimizer_session_id`.

5. **Introducir lock distribuido o serialización por sesión.**
   Por ejemplo cola por `session_id` o lock con Redis para turnos concurrentes de una misma sesión.

6. **Añadir ownership/authz.**
   El optimizer no debería listar sesiones globales de otros usuarios salvo rol explícito de staff.

7. **Hacer bootstrap explícito y obligatorio en cada entrada pública.**
   Que el cliente siempre envíe `context_id/public_slug` + identidad única; no depender de defaults peligrosos.

## 16. Fixes estructurales recomendados

1. **Separar claramente control plane y data plane.**
   - API stateless.
   - Estado conversacional en DB/Redis.
   - workers asíncronos fuera del proceso web.

2. **Modelo de identidad y tenancy real.**
   - `user_id` autenticado,
   - `session_id` opaco generado por servidor,
   - ownership checks por recurso.

3. **Persistencia explícita del canónico.**
   Guardar por sesión/conversation:
   - canonical state,
   - thread state OpenAI,
   - recent dialogue,
   - trace index.

4. **Diseño replica-safe de evaluación.**
   - cola externa,
   - repositorio durable,
   - workers independientes,
   - polling contra DB.

5. **Diseño replica-safe del optimizer.**
   - overrides persistidos,
   - sessions/sandboxes persistidos,
   - artifacts temporales fuera del filesystem local si deben sobrevivir.

6. **Política formal de limpieza y continuidad.**
   Definir qué resetea exactamente:
   - nueva conversación,
   - clone,
   - reopen,
   - surface switch,
   - finalización de episodio.

## 17. Veredicto final honesto

Si mañana despliegas esto en Railway para varios usuarios simultáneos y múltiples contextos/UI activas:

### Aguantará razonablemente bien
- resolución de contextos oficiales,
- separación lógica de superficies,
- trazabilidad contextual de cada turno,
- demos locales/controladas con una sola instancia.

### Es probable que explote o se degrade fuerte
- continuidad conversacional bajo varias réplicas,
- polling/recuperación de evaluación,
- consistencia del optimizer,
- privacidad y aislamiento si se mantienen los IDs públicos por defecto,
- comportamiento concurrente sobre una misma sesión.

**Conclusión final:** la base conceptual de multicontexto está bastante mejor que la base operacional de multiusuario/railway. El sistema **todavía depende de RAM local, single-instance y persistencia accidental del proceso** para piezas críticas. Antes de considerarlo “production ready” en Railway multiusuario real, hay que mover sesión, evaluación y optimizer a persistencia/coordi nación externas y cerrar el problema de identidad compartida por defecto.
