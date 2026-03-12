# Diagnóstico exhaustivo de conexiones/wiring alrededor del executor (HEAD vs `a1939b2`)

## 0) Resumen ejecutivo

### Veredicto corto
- **No encontré diferencias de wiring/backend en la ruta real del executor entre `HEAD` y `a1939b2`** en los archivos críticos de orquestación, guardrails, nodos, pipeline y servicio de sandbox: están byte-a-byte idénticos.
- **Sí encontré cambios de superficie/frontend path posteriores a `a1939b2`** (commit `8ca5e28`): se añadió `/interfaz_usuario` y se extrajo runtime compartido (`chat_runtime.js`) para `/optimizador` + `/interfaz_usuario`.
- Esos cambios **no alteran el core cognitivo del executor**, pero **sí unifican y amplifican la exposición** del mismo comportamiento de última milla a más entrypoints.
- Por tanto, la hipótesis “el deterioro viene de nuevas conexiones backend del executor respecto a `a1939b2`” queda **refutada para ese rango temporal**. La hipótesis “la unificación de superficies propagó el fallo existente” queda **confirmada**.

## 1) Hipótesis evaluadas

1. H1 — La degradación principal viene de cambios backend de conexiones/wiring del executor posteriores a `a1939b2`.
2. H2 — El executor hoy recibe distinto contexto útil por cambios de ensamblado de `executor_input` tras `a1939b2`.
3. H3 — El postproceso/guards/fallback del output del executor cambió después de `a1939b2`.
4. H4 — Cambios de rutas/frontend (`/optimizador`, `/interfaz_usuario`, `/avatar`) explican mayor visibilidad del problema.
5. H5 — El executor parece culpable, pero la causa está en otra conexión externa cambiada recientemente.

## 2) Metodología y evidencia usada

- Inspección estática de call graph actual y baseline `a1939b2`.
- Diff semántico + textual en archivos críticos de rutas/backend/orquestación.
- Verificación histórica con `git log`, `git diff`, `git show`, `git cat-file`.
- Verificación de invariantes con tests diagnósticos históricos nuevos.

## 3) Mapa de flujo actual (HEAD)

### 3.1 Superficie `/avatar` (modo negociación)
1. `avatar_app/app.js` resuelve endpoint por modo: negociación → `/negociar`.
2. `api/app.py` endpoint `/negociar` llama `run_negotiation_agent`.
3. `negociacion/pipeline.py` delega en `run_negotiation_cognitive_turn`.
4. `flow_config.py` ejecuta memory + phase, luego planner, luego executor.
5. Se aplica `run_output_guardrails` al `ExecutorOutput`.
6. Se devuelve `reply = executor_output.spoken_text`.

### 3.2 Superficie `/optimizador` (tab Chat)
1. `optimizador/app.js` usa runtime compartido `createOptimizadorChatRuntime`.
2. Runtime llama `/api/optimizador/sandbox/turn`.
3. Router `optimizador/__init__.py` delega en `services.run_sandbox_turn`.
4. `run_sandbox_turn` llama `run_negotiation_cognitive_turn` (mismo core).
5. Se devuelve `reply` del mismo pipeline.

### 3.3 Superficie `/interfaz_usuario`
1. `interfaz_usuario/app.js` también usa `createOptimizadorChatRuntime`.
2. Recorre el mismo endpoint `/api/optimizador/sandbox/turn`.
3. Ejecuta el mismo servicio y pipeline que `/optimizador`.

## 4) Mapa de flujo en `a1939b2`

- El núcleo backend de negociación es el mismo en los archivos auditados.
- `/optimizador` ya usaba `/api/optimizador/sandbox/turn` con `scope_turn_id`.
- `/avatar` ya usaba `/negociar` para negociación.
- **No existía** `/interfaz_usuario` ni `shared/chat_runtime.js`.

## 5) Diff de conexiones/wiring: HEAD vs `a1939b2`

## 5.1 Núcleo backend del executor (resultado)

Archivos comparados byte-a-byte: idénticos entre `HEAD` y `a1939b2`:
- `negociacion/orchestration/flow_config.py`
- `negociacion/guards/output.py`
- `negociacion/guards/policy.py`
- `negociacion/pipeline.py`
- `negociacion/optimizador/__init__.py`
- `negociacion/optimizador/services.py`
- `negociacion/nodes/executor_node.py`
- `negociacion/nodes/planner_node.py`
- `negociacion/nodes/memory_node.py`

### 5.2 Cambios reales detectados tras `a1939b2`

Un único commit relevante para superficies de chat (`8ca5e28`):
- añade mount estático `/interfaz_usuario` en `api/app.py`;
- crea `avatar_app/interfaz_usuario/app.js`;
- extrae runtime compartido `avatar_app/shared/chat_runtime.js`;
- migra `optimizador/app.js` para consumir ese runtime.

### 5.3 ¿Cambió el camino útil de ejecución del executor?

- **No en backend**: el camino final llega al mismo `run_negotiation_cognitive_turn`.
- **Sí en frontend/superficie**: ahora dos UIs (`/optimizador` y `/interfaz_usuario`) usan la misma ruta útil y misma semántica de envío.

## 6) Tabla comparativa por ejes

| Eje | HEAD | `a1939b2` | Igual/Diferente | Evidencia | Impacto potencial | Severidad | Archivo/función | Hipótesis |
|---|---|---|---|---|---|---|---|---|
| endpoint/path útil (`/optimizador`) | `/api/optimizador/sandbox/turn` | mismo | Igual | app optimizador + runtime/inline | Sin cambio de core | Baja | `optimizador/app.js`, `shared/chat_runtime.js` | Refuta H1 |
| endpoint/path útil (`/interfaz_usuario`) | existe, usa sandbox/turn | no existe | Diferente | mount + nuevo app | Amplifica superficie | Media | `api/app.py`, `interfaz_usuario/app.js` | Confirma H4 |
| endpoint/path útil (`/avatar`) | negociación→`/negociar` | mismo | Igual | `fetchAgentReply` | Sin cambio del core | Baja | `avatar_app/app.js` | Refuta H1 |
| service call de sandbox | `run_sandbox_turn` | mismo | Igual | byte-identical | Sin deriva | Baja | `optimizador/services.py` | Refuta H1/H2 |
| orchestration function | `run_negotiation_cognitive_turn` | misma | Igual | byte-identical | Sin deriva | Crítica (por importancia) | `pipeline.py`, `flow_config.py` | Refuta H1 |
| ensamblado `executor_input` | igual campos/fuentes | igual | Igual | byte-identical | No explica regresión post-`a1939b2` | Alta | `flow_config.py::build_executor_input` | Refuta H2 |
| `selected_memory_for_reference` | igual selección | igual | Igual | byte-identical | No cambio | Media | `_select_memory_for_executor` | Refuta H2 |
| `response_limits` | desde planner.limits | igual | Igual | byte-identical | No cambio | Media | `build_executor_input` | Refuta H2 |
| `scene_state` en executor input | incluido | igual | Igual | byte-identical | No cambio | Media | `build_executor_input` | Refuta H2 |
| planner handoff→executor | mismo orden/flujo | mismo | Igual | byte-identical | No cambio | Alta | `run_negotiation_cognitive_turn` | Refuta H1 |
| output validation | structured JSON + pydantic | igual | Igual | byte-identical | No cambio | Alta | `_call_structured` | Refuta H3 |
| output guardrails | misma lógica | igual | Igual | byte-identical | No cambio | Alta | `guards/output.py` | Refuta H3 |
| fallback behavior | mismo `_executor_fallback` | igual | Igual | byte-identical | No cambio | Media | `_executor_fallback` | Refuta H3 |
| request context (`conversation_id`/`previous_response_id`) | misma política | igual | Igual | byte-identical | No cambio | Alta | `flow_config.py` threading/context | Refuta H1/H2 |
| frontend runtime | runtime compartido | inline en optimizador | Diferente | diff `8ca5e28` | Cambia superficie, no core | Media | `shared/chat_runtime.js` | Confirma H4 |
| `scope_turn_id` envío sandbox | sí | sí | Igual | baseline/HEAD | No cambio de contexto principal | Media | optimizador inline vs runtime | Refuta H5 fuerte |

## 7) Hallazgos confirmados

1. **No hay drift backend del executor y su entorno inmediato entre `a1939b2` y HEAD** en los archivos críticos auditados.
2. **La diferencia histórica relevante en este rango es de superficie/path frontend** (interfaz nueva + runtime compartido), no de motor cognitivo.
3. La unificación de runtime **sí puede propagar** el mismo comportamiento defectuoso preexistente a más entrypoints.

## 8) Hallazgos descartados

1. Que exista un cambio post-`a1939b2` en `build_executor_input` que altere su contenido útil.
2. Que exista un cambio post-`a1939b2` en `run_output_guardrails` o fallback que explique por sí solo mayor permisividad reciente.
3. Que `/optimizador` haya pasado recientemente de bypass a usar executor dentro de este rango: ya estaba en el mismo core.

## 9) Candidatos causales priorizados (respecto a la tesis de conexiones)

### Candidato A (más fuerte en este rango): propagación por unificación de superficies
- Commit `8ca5e28` extiende el mismo flujo de chat a `/interfaz_usuario` y centraliza runtime.
- No rompe el executor, pero multiplica dónde se observa su comportamiento.

### Candidato B (no confirmado en este rango): causa raíz previa a `a1939b2`
- Como el core es idéntico entre baseline y HEAD, si hay degradación real de “última milla” por wiring backend, su introducción sería **anterior** a `a1939b2` o fuera del rango comparado.

## 10) Respuestas directas a tus 10 preguntas

1. ¿Se llama igual? **Sí**, en backend crítico auditado.
2. ¿Recibe mismo input útil? **Sí** (ensamblado idéntico).
3. ¿Mismo assembly/fuentes/orden? **Sí** en `build_executor_input` y handoff.
4. ¿Cambios en planner_output/memory/limits/scene/threading/guards/fallback? **No** post-`a1939b2` en archivos críticos.
5. ¿Diferencias de routing entre superficies? **Sí**: se agrega `/interfaz_usuario` y runtime compartido; `/avatar` mantiene `/negociar`.
6. ¿Cambio indirecto fuera del executor que lo haga parecer culpable? **Sí** a nivel de exposición de superficie (unificación UI path), **no** a nivel de wiring backend core.
7. ¿Cambio post-`a1939b2` que aumente meta-preguntas por contexto backend? **No hallado** en backend core.
8. ¿Cambio de wiring/postproceso para salida distinta? **No** en core; **sí** cambio de superficie.
9. ¿Diferencias de enforcement planner→executor entre ambas versiones? **No** en el rango comparado (idéntico).
10. ¿Commit más candidato post-`a1939b2`? **`8ca5e28`** por propagación de superficie, no por alterar lógica del executor.

## 11) Veredicto final

**Hay mezcla, pero el candidato causal principal en el rango `a1939b2..HEAD` NO es un cambio de conexiones backend del executor**. El core de ejecución está igual. **La diferencia real es de wiring de superficies/frontend compartidas**, que incrementa la exposición del mismo comportamiento.

Dicho de forma inequívoca:
- Si la degradación que observas es nueva estrictamente “desde después de `a1939b2`”, la explicación más fuerte es **propagación por unificación de rutas UI**.
- Si la degradación proviene del core executor/wiring backend, su causa raíz está **antes de `a1939b2`** (o fuera de este repo/rango), porque en este rango no hay cambios de core.

## 12) Plan mínimo de corrección (posterior al diagnóstico)

1. **P0**: mantener este diagnóstico como baseline y no tocar prompts todavía.
2. **P0**: añadir trazas comparables por superficie (avatar/opt/interfaz) en producción para cuantificar divergencias de input real por turno.
3. **P1**: si se confirma que el problema existía ya en `a1939b2`, ampliar arqueología a commits previos donde se introdujo `flow_config`/guardrails actuales.
4. **P1**: solo después, endurecer enforcement contractual planner→executor (ya diagnosticado previamente) con tests de no-regresión.
