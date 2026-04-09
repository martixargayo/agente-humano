# Auditoría end-to-end de `conversacion_simple` (2026-04-09)

## Alcance
Auditoría transversal del flujo real de `conversacion_simple` desde superficies (`interfaz_usuario`, `optimizador`) hasta llamada a provider, parsing, fallback, persistencia y trazas.

## 1) Mapa del flujo real

### 1.1 Entrada por `interfaz_usuario`
1. `POST /api/interfaz_usuario/negociacion/turn` entra por router de `interfaz_usuario`.  
2. `interfaz_usuario.services.run_turn()` carga sesión, valida ownership de superficie y contexto bound.  
3. Si el contexto bound es `conversacion_simple`, construye config con `build_conversacion_simple_pipeline_config(context_id=..., stateful=True)`.  
4. Construye `turn_context` con `build_conversacion_simple_turn_context(...)`.  
5. Ejecuta `run_conversacion_simple_turn(...)`.  
6. Empaqueta `meta` sintético para contrato de entrada y devuelve respuesta.

### 1.2 Entrada por `optimizador`
1. `POST /api/optimizador/sandbox/turn` entra por router de `optimizador`.  
2. `optimizador.services.run_sandbox_turn()` asegura sesión/superficie, resuelve contexto base con `context_bridge.ensure_optimizer_session_context`.  
3. Selecciona adapter por `flow_id` (`get_adapter`).  
4. Si `flow_id == conversacion_simple`, usa `build_conversacion_simple_pipeline_config(..., stateful=True)`; opcionalmente aplica overrides vía `experiments_bridge.apply_overrides(...)`.  
5. Adapter `ConversacionSimpleOptimizerAdapter.run_sandbox_turn()` construye `turn_context` y llama `run_conversacion_simple_turn(...)`.  
6. `optimizador` agrega metadatos de intento/probe, y persiste trazas de intento aparte.

### 1.3 Núcleo `run_conversacion_simple_turn`
1. `_validate_turn_context()` exige: contexto bound en sesión == `turn_context.effective_context_id` == `config.context_id` == contexto derivado de `prompts_dir`.  
2. Carga estado canónico y diálogo reciente con `ConversationSimpleStateRepository`.  
3. Carga prompt de brain (`brain_prompt.txt`) y prompt de summarizer (archivo o default embebido).  
4. Agrega mensaje usuario al estado y al `recent_dialogue`.  
5. Trim por turnos; si archiva turnos dispara summarizer estructurado (`SummarizerOutput`).  
6. Construye `BrainInput`, llama `_call_brain_structured()` con schema normalizado estricto.  
7. Parsea/coacciona salida (incluyendo compat legacy), aplica patch al estado.  
8. Agrega assistant al diálogo, segundo trim de invariante, mantenimiento de memoria.  
9. Construye `ConversationSimpleTurnTrace`, persiste estado+trace y retorna reply/meta.

## 2) Hallazgos confirmados

### H1. Sí hay dos rutas de entrada distintas (interfaz y optimizador) que convergen al mismo runtime core, pero con capas no equivalentes.
- Convergen en `run_conversacion_simple_turn`, pero `optimizador` tiene capas extra (overrides, probe, attempt-traces, clone/new-conversation strategy).  
- `interfaz_usuario` no aplica `experiments_bridge`, ni `begin_turn_probe/end_turn_probe`, ni trazas de intento.

**Riesgo:** “mismo turno” no implica mismo entorno efectivo entre superficies.

### H2. El helper de turn context de `conversacion_simple` fija `entry_surface="conversacion_simple"` para todas las superficies.
- Tanto `interfaz_usuario` como `optimizador` llaman el mismo builder `build_conversacion_simple_turn_context(...)`.  
- Ese builder hardcodea `entry_surface="conversacion_simple"` y `context_source="internal_explicit"`.

**Riesgo:** pérdida de trazabilidad de superficie real en runtime; complica forensics de drift entre caller real (IU/optimizador) y contexto de ejecución.

### H3. `optimizador` sí puede cambiar el paquete efectivo de prompts/assets/config de `conversacion_simple`.
- `apply_overrides` crea tempdir y reemplaza `prompts_dir` en config para `conversacion_simple`.  
- También puede inyectar overrides contextuales (persona) directo en `world_state[memory_key]`.

**Riesgo:** comparativas IU vs optimizador pueden no ser equivalentes aunque compartan `run_conversacion_simple_turn`.

### H4. No hay duplicación de normalización strict-schema en `conversacion_simple` (single source infra), pero sí wrappers locales duplicados por flujo.
- `conversacion_simple` y `negociacion` tienen wrapper local `_normalize_schema_for_strict_json_schema` que delega al helper común de `infra`.  
- No hay evidencia de normalizador alternativo activo para CS.

**Riesgo:** bajo hoy; medio a futuro por duplicación de puntos de invocación y potencial divergencia si uno empieza a mutar localmente.

### H5. Brain y summarizer no son homogéneos en fallback/parseo/observabilidad, por diseño y con implicaciones.
- Brain: parse JSON dict + coerce legado + fallback social específico.  
- Summarizer: valida contra `SummarizerOutput`, fallback determinístico por formateo textual de turnos archivados.

**Riesgo:** semánticas de fallback distintas pueden ocultar problemas reales del provider en una etapa más que en otra.

### H6. Persistencia y selección de trazas en `optimizador` depende de prioridad por contexto bound.
- `resolve_traces` prioriza keys distintas según si existe binding negociación o CS; además tiene fallback por cualquier `*_traces`.

**Riesgo:** en estados contaminados/mixtos podría leerse una serie de trazas no esperada por caller.

### H7. Existen rutas legacy activas fuera de superficies parity-safe.
- App mantiene `/chat` y `/negociar` (deprecated), mientras nuevas superficies están en `/api/interfaz_usuario/*` y `/api/optimizador/*`.

**Riesgo:** debugging confuso por coexistencia de rutas nuevas + legacy, especialmente en despliegues con clientes heterogéneos.

## 3) Comparativa Brain vs Summarizer (CS)

| Aspecto | Brain | Summarizer |
|---|---|---|
| Modelo default | `gpt-5.4` | `gpt-5.4-nano` |
| Schema base | `BrainOutput` | `SummarizerOutput` |
| Normalización strict | Sí (`_prepare_strict_schema`) | Sí (`_prepare_strict_schema`) |
| Validación preflight | Sí | Sí |
| Parse | `json.loads` + dict + coerción legacy + validate pydantic | `json.loads` + `SummarizerOutput.model_validate` |
| Fallback | `brain_fallback` (salidas sociales + clarify) | Resumen determinístico texto de turnos archivados |
| Observabilidad | `brain_schema_observability`, provider_exception, fallback_reason_code | `summarizer_schema_observability`, provider_exception, fallback_reason_code |
| Impacto trazas | nodo `brain` + memory_obs | memory_obs (no nodo separado explícito) |

Conclusión: comparten infra de schema strict, pero su semántica de degradación y de salida no es homogénea.

## 4) Comparativa `interfaz_usuario` vs `optimizador` para CS

### Coincidencias reales
- Ambos terminan llamando `run_conversacion_simple_turn` con config stateful y `turn_context` explícito.
- Ambos exigen contexto bound/consistente antes de ejecutar.

### Diferencias reales (materiales)
- `optimizador`:
  - Resuelve contexto con `context_bridge` multi-flow.
  - Aplica overrides de prompt/config/contextual.
  - Añade telemetría de intento (`backend_turn_attempt_id`, probes provider/side-effects).
- `interfaz_usuario`:
  - Ruta pública con resolución de slug/contexto y posibles auto-reset/new conversation.
  - No usa overrides de experimentos.
  - Meta de retorno construida localmente para CS (no sale del pipeline).

## 5) Config/contextos/prompts: baseline vs `negociacion_sala_reuniones`

- Resolución de contextos CS es por carpeta oficial + `manifest.json`; `build_conversacion_simple_pipeline_config` toma `prompts_dir` del contexto resuelto.
- En optimizador, overrides pueden reemplazar `prompts_dir` por tempdir generado.
- `_validate_turn_context` verifica coherencia `session_binding`/`config.context_id`/`prompts_dir`; esto protege contra gran parte del drift accidental.

## 6) Runtime/deploy consistency

- `runtime_version` se inyecta en observabilidad de schema y en traces (`get_runtime_version_info()`).
- Fuente de versión puede venir de env (`GIT_COMMIT/COMMIT_SHA`) o git local (`git rev-parse`).
- Arranque (Procfile/nixpacks) apunta a un único `uvicorn api.app:app`, pero en despliegues multi-réplica no hay, en este repo, un mecanismo explícito de “build fingerprint enforcement per replica” en responses.

Conclusión: hay base para diagnóstico (runtime_version), pero falta cierre fuerte para detectar heterogeneidad entre réplicas en producción real.

## 7) Zonas sanas vs zonas frágiles

### Zonas sanas
- Guardrails de coherencia de contexto en `_validate_turn_context`.
- Normalización/validación strict centralizada en `infra.openai.structured_outputs`.
- Separación de superficies por `_session_surface` para evitar mezcla directa IU/optimizador/comunicación.

### Zonas frágiles
- Context builder CS no conserva `entry_surface` real del caller.
- Overrides de optimizador alteran runtime efectivo (prompts/assets/config/state), lo que rompe comparabilidad naive con IU.
- Convivencia de rutas legacy (`/chat`, `/negociar`) y nuevas superficies puede inducir diagnósticos cruzados erróneos.

## 8) Hipótesis plausibles no confirmadas

1. **Drift por réplica de despliegue**: misma API pública sirviendo réplicas con código diferente puede explicar “local OK / runtime invalid_json_schema”.
2. **Estados contaminados históricos**: aunque hay checks de surface/context, `resolve_traces` con fallback por keys podría leer trazas no previstas en estados antiguos/no migrados.
3. **Diferencia de entorno SDK/provider**: misma ruta lógica pero distinto entorno de ejecución (SDK/model rollout) podría gatillar `invalid_json_schema` en runtime y no en local.

## 9) Recomendaciones priorizadas

1. **Preservar superficie real en `TurnExecutionContext` para CS** (no hardcodear `entry_surface="conversacion_simple"`).
2. **Emitir fingerprint de runtime/build en respuestas de turn o headers diagnósticos** para correlacionar réplicas.
3. **Añadir “effective_payload_snapshot hash” para schema enviado al provider** (brain/summarizer) en trace persistente, no solo logs.
4. **Crear prueba de paridad IU vs optimizador para CS con y sin overrides** (assert de equivalencia fuerte).  
5. **Marcar y aislar rutas legacy** (`/chat`, `/negociar`) en observabilidad para evitar contaminación de diagnósticos.

