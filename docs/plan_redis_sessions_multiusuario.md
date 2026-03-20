# Plan Redis sessions multiusuario

## Resumen ejecutivo

La idea base es **correcta** para este repositorio y para tu caso real, pero necesita dos ajustes para ser realmente segura:

1. **Redis no debe guardar solo un `conversation_id`; debe guardar el snapshot operativo mínimo completo de la sesión**, porque el pipeline actual no depende solo de OpenAI. Depende también de `planner_state`, `memory_working`, `negotiation_state`, `selected_memory`, `recent_dialogue`, binding de contexto y binding de superficie.
2. **El lock por sesión no es opcional**. En este repo ya hay evidencia de colisión a nivel OpenAI (`conversation_locked`) y, además, el pipeline muta el mismo objeto de estado en varios puntos del turno. Sin lock, mover el estado a Redis no elimina las carreras; solo las desplaza.

Si se implementa como:
- IDs únicas generadas por backend,
- store compartido en Redis,
- snapshot mínimo de sesión por clave,
- continuidad OpenAI por sesión,
- lock Redis por sesión,
- TTL renovable,

entonces **sí** es una solución mínima, razonable y proporcionada para tu objetivo principal: que varios usuarios jueguen a la vez desde distintos equipos y que cada partida se comporte como si fuera la única.

## Veredicto sobre la idea

### Lo acertado

1. **IDs únicas siempre.**
   Es imprescindible, porque hoy el repo sigue exponiendo defaults compartidos para la interfaz pública.

2. **Sacar la partida viva de la RAM local.**
   Es el cambio estructural mínimo correcto. Tu problema real no es “persistencia histórica”; es “continuidad correcta entre réplicas”.

3. **Redis como store temporal compartido.**
   Encaja mejor que Postgres para este objetivo concreto porque:
   - el estado es temporal,
   - necesitas acceso rápido por clave,
   - necesitas TTL,
   - necesitas lock distribuido,
   - no quieres persistencia histórica pesada.

4. **Continuidad OpenAI por sesión.**
   Encaja muy bien con la arquitectura actual porque el repo ya modela `openai_thread` y ya soporta `conversation_id` y `previous_response_id`.

5. **TTL por sesión.**
   Es buena idea siempre que se renueve solo en actividad real y se permita borrado explícito al cerrar o finalizar.

### Lo incompleto o peligroso

1. **Redis no puede limitarse a “guardar conversación OpenAI”.**
   En este repo eso sería insuficiente. El flujo actual usa estado local propio del dominio para decidir la respuesta, no solo el contexto remoto de OpenAI.

2. **No conviene usar un lock demasiado corto.**
   El pipeline hace varias llamadas LLM y puede tardar segundos. Si el lock expira antes del final del turno, reaparece la carrera.

3. **No conviene rehidratar un estado parcial mal definido.**
   Si guardas `conversation_id` pero no `planner_state` o `recent_dialogue`, el modelo podría seguir la conversación remota mientras el planner local pierde continuidad táctica.

4. **No hay que migrar toda evaluación/optimizer al mismo nivel ahora mismo.**
   Pero sí hay que evitar que rompan el runtime principal o generen una falsa sensación de seguridad. Para tu objetivo mínimo, el foco debe estar en la superficie pública y el runtime principal.

## Arquitectura mínima propuesta

### Componentes
- **Servicio web Railway**: FastAPI actual.
- **Redis gestionado en Railway**: store temporal compartido.
- **OpenAI Responses + Conversations**: continuidad duradera por conversación.

### Patrón operativo
Cada request de turno hace esto:
1. recibe `session_id` opaco;
2. adquiere lock Redis `lock:session:{session_id}`;
3. carga snapshot de sesión desde Redis;
4. valida `context_id` y `surface`;
5. ejecuta el pipeline de negociación actual;
6. reutiliza o crea `openai_conversation_id`;
7. guarda snapshot actualizado;
8. renueva TTL;
9. libera lock;
10. responde.

### Qué persiste temporalmente
Solo lo necesario para continuar la partida viva:
- identidad opaca de la sesión,
- contexto/surface fijados,
- canonical state,
- recent dialogue,
- traces mínimas o índice,
- continuidad OpenAI,
- timestamps de actividad.

### Qué NO hace falta meter ahora
- histórico largo completo,
- base de datos analítica,
- bucket de artifacts,
- refactor total del optimizer,
- warehouse de evaluación.

## Por qué encaja con este caso real

Porque tu caso pide exactamente:
- aislamiento por partida,
- continuidad correcta,
- multiusuario concurrente,
- compatibilidad con réplicas,
- cero dependencia de la RAM local,
- caducidad natural del estado.

Redis resuelve lo que hoy falla:
- **shared state cross-replica**,
- **TTL nativo**,
- **locking distribuido**,
- **latencia baja por sesión**.

Y OpenAI Conversations encaja porque ya usas `ThreadMode.conversation` como default en el runtime actual.

## Qué riesgos resuelve

1. Colisión de usuarios por defaults compartidos.
2. Pérdida de continuidad al cambiar de réplica.
3. Reanudación rota tras restart del proceso web.
4. Carreras de doble turno sobre una misma sesión.
5. Dependencia de `SESSIONS` en RAM.
6. Dependencia implícita de single-instance.

## Qué riesgos mantiene

1. **Serialización incorrecta del snapshot.**
   Si se serializa/deserializa mal, puedes introducir residuos nuevos.

2. **Locks mal calibrados.**
   Si el lock caduca antes de acabar el turno, reaparece la contaminación concurrente.

3. **TTL demasiado agresivo.**
   Puede matar partidas activas si el usuario tarda demasiado entre turnos.

4. **Optimizer/evaluación siguen sin endurecer si se usan en producción multiusuario.**
   Para el objetivo mínimo no es bloqueante, pero conviene dejarlos fuera del camino crítico o marcarlos como no replica-safe.

## Comparación con arquitectura actual

### Actual
- `SESSIONS` global en proceso.
- bootstrap público con IDs compartidas.
- estado canónico y recent dialogue dentro de `world_state` en RAM.
- continuidad OpenAI también dentro de ese estado local.
- evaluación in-memory.
- optimizer con overrides in-memory.

### Propuesta mínima
- `SessionStore` abstracto.
- `RedisSessionStore` como implementación Railway.
- IDs únicas emitidas por backend.
- snapshot de sesión compartido y con TTL.
- continuidad OpenAI persistida por sesión.
- lock Redis por sesión.
- pipeline funcional casi igual.

## Plan por fases

### Fase 0. Validación y preparación
**Objetivo:** congelar el contrato mínimo de la sesión viva.

**Por qué existe:** si migras sin fijar qué es “estado imprescindible”, puedes romper continuidad táctica.

**Riesgos:** mover demasiado poco o demasiado estado.

**Archivos afectados:**
- `backend/sessions/state.py`
- `backend/negociacion/state/canonical_state.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/interfaz_usuario/services.py`

**Cambios exactos:**
- inventariar campos mínimos del snapshot;
- decidir si `history` sigue siendo necesaria o si se deriva de `recent_dialogue` + trazas.

**Criterio de aceptación:**
- lista cerrada de campos que deben sobrevivir entre requests y réplicas.

### Fase 1. IDs únicas y bootstrap seguro
**Objetivo:** eliminar por completo identidades públicas compartidas.

**Archivos afectados:**
- `backend/interfaz_usuario/models.py`
- router/bootstrap de `interfaz_usuario`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`

**Cambios exactos:**
- quitar defaults compartidos del modelo;
- permitir bootstrap sin IDs entrantes;
- generar IDs opacas en backend;
- devolverlas al frontend y persistirlas en memoria local del navegador durante esa partida.

**Criterio de aceptación:**
- dos navegadores nuevos jamás comparten `user_id` ni `session_id`.

### Fase 2. Abstracción de SessionStore
**Objetivo:** desacoplar el runtime de `SESSIONS`.

**Archivos afectados:**
- `backend/sessions/state.py`
- call-sites en `interfaz_usuario`, `negociacion`, `evaluacion`, `optimizador`.

**Cambios exactos:**
- introducir `SessionStore`;
- mantener `InMemorySessionStore` para local/tests;
- hacer que `get_session_state`/`save_session_state` deleguen en el store activo.

**Criterio de aceptación:**
- ningún módulo del path crítico de negociación lee/escribe `SESSIONS` directamente.

### Fase 3. RedisSessionStore
**Objetivo:** mover la partida viva a Redis.

**Archivos afectados:**
- nuevo módulo `backend/sessions/store.py` o similar;
- config/env loading;
- wiring en `api/app.py` o bootstrap backend.

**Cambios exactos:**
- conectar `REDIS_URL`;
- implementar get/save/delete/touch;
- serializar snapshot JSON de sesión.

**Criterio de aceptación:**
- restart del web process no borra una sesión activa.

### Fase 4. Continuidad OpenAI por sesión
**Objetivo:** persistir continuidad LLM fuera de la RAM local.

**Veredicto técnico:** para este repo, **prefiero `conversation_id`** a `previous_response_id`.

**Por qué:**
- el código ya está sesgado a `ThreadMode.conversation`;
- `build_openai_request_context` ya prioriza `conversation`;
- OpenAI documenta Conversations como el mecanismo duradero para Responses;
- la propia guía de OpenAI indica que con `previous_response_id` las `instructions` previas no se arrastran automáticamente si las gestionas así.

**Riesgo:** debes mantener el lock por sesión para evitar `conversation_locked`.

### Fase 5. Lock por sesión
**Objetivo:** serializar turnos de una misma partida.

**Archivos afectados:**
- endpoint principal de turno en `interfaz_usuario/services.py`
- posiblemente wrapper compartido del turno contractual.

**Cambios exactos:**
- `acquire(lock:session:{session_id})`;
- timeout corto + respuesta `409/423 session_busy` o retry controlado;
- `finally` para release.

**Criterio de aceptación:**
- dos requests simultáneos sobre la misma sesión no pisan estado ni trazas.

### Fase 6. TTL y cleanup
**Objetivo:** evitar persistencia histórica innecesaria.

**Cambios exactos:**
- TTL renovado en cada turno exitoso;
- delete explícito opcional al terminar;
- TTL distinta para sesión activa vs finalizada si quieres retener unos minutos para feedback final.

**Criterio de aceptación:**
- una sesión abandonada desaparece sola sin afectar sesiones activas.

### Fase 7. Hardening y tests
**Objetivo:** demostrar que el flujo no se degrada.

**Cambios exactos:**
- tests de réplica-like,
- tests de lock,
- tests de TTL,
- tests de rehidratación,
- tests de continuidad OpenAI.

### Fase 8. Rollout controlado
**Objetivo:** migrar sin sustos.

**Cambios exactos:**
- feature flag para store Redis;
- staging con tráfico real limitado;
- métricas de locks, expiraciones, misses y rehidratación.

## Impacto sobre negociación

### Lo que debería seguir igual
- prompts,
- fases,
- planner/executor,
- binding de contexto,
- surface contract,
- guardrails,
- formato de trazas.

### Lo que sí cambia de verdad
- el sitio donde vive el snapshot;
- la forma de cargar y guardar sesión;
- el manejo de concurrencia;
- el bootstrap de identidad.

### Riesgo real de degradación
No está en Redis en sí. Está en:
- guardar un snapshot incompleto,
- rehidratar con defaults cuando no toca,
- perder `recent_dialogue` o `planner_state`,
- tratar el lock como decorativo.

## Riesgos de residuos/contaminación

1. **Estado viejo revivido por error.**
   Si reciclas `session_id`, reaparecen residuos antiguos.

2. **Estado parcial.**
   Si guardas `conversation_id` pero no el canónico, la táctica local queda desincronizada.

3. **Deserialización laxa.**
   Si aceptas payload corrupto o antiguo sin validación, puedes propagar residuos invisibles.

4. **Lock caducado prematuramente.**
   Puede permitir dos turnos simultáneos sobre el mismo `conversation_id`.

## Plan de pruebas

1. Dos navegadores nuevos → IDs distintas.
2. Dos usuarios simultáneos → sesiones y trazas separadas.
3. Dos contextos distintos → binding correcto persistido en Redis.
4. Mismo usuario, doble click → un turno gana y el otro recibe `busy` o espera.
5. Request A / réplica 1 y request B / réplica 2 → continuidad correcta.
6. Restart del backend → la partida sigue.
7. TTL expira sesión inactiva → desaparece.
8. TTL se renueva con actividad → no desaparece en mitad de la partida.
9. Rehidratación de `planner_state`, `memory_working`, `negotiation_state`, `recent_dialogue` → igual que antes del restart.
10. Continuidad OpenAI → mismo `conversation_id` durante toda la partida.

## Recomendación final honesta

Sí: **tu idea mínima va en la dirección correcta y es suficiente para el objetivo real**, siempre que la aterrices como:
- Redis para el snapshot mínimo completo de la sesión viva,
- `conversation_id` por sesión como mecanismo preferente de continuidad OpenAI,
- lock distribuido por sesión,
- IDs opacas generadas por backend,
- TTL renovable,
- rollout gradual con `InMemorySessionStore` solo para local/test.

Lo que no te recomiendo es quedarte a medias con una solución “Redis solo para unas pocas cosas”. En este repo, o sacas **toda la partida viva** del proceso web, o seguirás teniendo continuidad frágil y residuos difíciles de explicar.
