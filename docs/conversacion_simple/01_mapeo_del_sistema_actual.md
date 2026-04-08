# 01 · Mapeo del sistema actual (`negociacion`) con evidencia de repo

> Este documento separa **hechos observados** del estado actual y evita propuestas de implementación.

---

## 1) Arquitectura backend relevante

### Hechos observados

- App principal FastAPI en `backend/api/app.py`.
- Se montan routers de:
  - `optimizador` (`negociacion.optimizador.router`),
  - `interfaz_usuario` (`interfaz_usuario.router`),
  - `comunicacion`.
- Conviven endpoints legacy (`/chat`, `/negociar`) con superficies nuevas.

### Evidencia

- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/services/legacy_negociar_service.py`

---

## 2) Superficies que llaman al runtime de negociación

## 2.1 `interfaz_usuario`

### Hechos observados

- Endpoints: bootstrap, turn, finalize, new_conversation.
- Servicio usa lock por sesión, TTL lifecycle, binding de superficie, binding de contexto y ejecución contractual.
- Turno llama a:
  1. `build_negotiation_pipeline_config(..., stateful=True)`
  2. `build_interfaz_usuario_turn_context(...)`
  3. `execute_turn_with_contract(...)`

### Evidencia

- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/services/turn_context_factory.py`
- `backend/negociacion/orchestration/turn_contract.py`

## 2.2 `optimizador`

### Hechos observados

- Soporta bootstrap, turn sandbox, clone/new conversation, contexts, prompts, compare, evals.
- Reusa el mismo `execute_turn_with_contract` y el mismo builder de config.
- Inyecta metadata adicional `_optimizador` en traces.

### Evidencia

- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/orchestration/turn_contract.py`

## 2.3 Legacy `/negociar`

### Hechos observados

- Endpoint marcado deprecated.
- Exige `context_id` explícito para modo stateful.
- Aun así usa la misma tubería contractual (`execute_turn_with_contract`) vía servicio legacy.

### Evidencia

- `backend/api/app.py`
- `backend/negociacion/services/legacy_negociar_service.py`
- `backend/tests/test_api_negociar_context_contract.py`

---

## 3) Contrato de sesión/lifecycle/locks

## 3.1 TTL lifecycle

### Hechos observados

- TTLs por scope: `bootstrap`, `active`, `finalized` leídos de env.
- `apply_session_ttl` guarda metadatos en `_session_lifecycle` y toca TTL en store.
- Existe camino “lightweight touch” para refresco sin GET+SAVE extra.

### Evidencia

- `backend/sessions/lifecycle.py`
- `backend/tests/test_session_lifecycle_lightweight_touch.py`
- `backend/tests/test_phase6_phase7_session_lifecycle.py`

## 3.2 Lock de ejecución

### Hechos observados

- Lock por sesión (`session-lock:{user}:{session}`), backend memoria o Redis.
- Redis lock con heartbeat/refresh y retries por timeout de socket.
- Conflicto retorna `SessionBusyError` y superficies devuelven HTTP 423.

### Evidencia

- `backend/sessions/session_lock.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/optimizador/services.py`
- `backend/tests/test_session_redis_timeout_retries.py`

## 3.3 Surface ownership

### Hechos observados

- Una sesión queda ligada a una sola superficie (`interfaz_usuario`, `optimizador`, `comunicacion`).
- Si cambia superficie se devuelve conflicto 409.

### Evidencia

- `backend/sessions/surface_scope.py`
- `backend/tests/test_phase4_phase5_session_runtime.py`

---

## 4) Contrato de contexto actual

## 4.1 Resolución de contexto oficial

### Hechos observados

- Contextos oficiales de negociación viven en `backend/negociacion/contexts/<context_id>/`.
- `manifest.json` + paths requeridos (prompts y assets) determinan si un contexto es “oficial”.
- Hay fallback legacy para `baseline_current` cuando aplica.

### Evidencia

- `backend/negociacion/contexts/resolver.py`
- `backend/negociacion/contexts/baseline_current/manifest.json`
- `backend/negociacion/contexts/sala_reuniones/manifest.json`
- `backend/tests/test_phase1_baseline_context.py`
- `backend/tests/test_phase8_second_official_context.py`

## 4.2 Binding de contexto en sesión

### Hechos observados

- Se guarda en `world_state["negotiation_context"]`.
- Si la sesión ya está ligada y piden otro contexto -> conflicto (`SessionContextConflictError`).

### Evidencia

- `backend/negociacion/contexts/session_binding.py`
- `backend/negociacion/orchestration/context_errors.py`
- `backend/tests/test_phase3_context_session_binding.py`

## 4.3 Public mapping

### Hechos observados

- Mapea `public_slug` ↔ `context_id`.
- Soporta default cuando no se envía ninguno.
- Bloquea conflicto si llegan ambos y no coinciden.

### Evidencia

- `backend/negociacion/contexts/public_mapping.py`
- `backend/tests/test_phase4_public_context_surface.py`

## 4.4 Validación pre-ejecución

### Hechos observados

- `validate_turn_context_pre_execution` exige coherencia entre:
  - `turn_context.effective_context_id`,
  - contexto ligado en sesión,
  - contexto derivado de `config`,
  - contexto inferido por `prompts_dir`.
- Si hay mismatch falla temprano con errores tipados.

### Evidencia

- `backend/negociacion/orchestration/turn_context_validator.py`
- `backend/negociacion/orchestration/flow_config.py` (`derive_config_context_id`)
- `backend/tests/test_turn_context_contract.py`
- `backend/tests/test_context_contract_topdown_regression.py`

## 4.5 Contrato de entrada de turno

### Hechos observados

- `execute_turn_with_contract` fuerza el precheck contextual y luego ejecuta runtime.
- Postejecución inyecta `_entry_contract` y `context_meta` en trace.

### Evidencia

- `backend/negociacion/orchestration/turn_contract.py`
- `backend/tests/test_phase5_context_traces.py`

---

## 5) Runtime de `negociacion` hoy

## 5.1 Configuración de pipeline

### Hechos observados

- `build_negotiation_pipeline_config` resuelve contexto y carga `prompts_dir` contextual.
- Config incluye modelos por nodo, flags de guardrails/traces, límites de contexto.

### Evidencia

- `backend/negociacion/orchestration/flow_config.py`
- `backend/tests/test_phase2_context_runtime_resolution.py`

## 5.2 Topología online del turno

### Hechos observados

- `run_negotiation_cognitive_turn` ejecuta:
  1. input guardrails,
  2. `memory` + `phase_classifier` en paralelo,
  3. `planner`,
  4. `executor`,
  5. output guardrails,
  6. persistencia de estado + trace.
- Threading policy explícita por nodo:
  - memory/phase `stateless_parallel`,
  - planner/executor `stateless_sequential`.

### Evidencia

- `backend/negociacion/orchestration/flow_config.py`

## 5.3 Prompting y Prompt IO mapping

### Hechos observados

- Prompts se cargan desde `prompts_dir` contextual.
- Se aplica `load_prompt_io_adapter(...)` si existe `prompt_io_mapping.json`.
- Adapter soporta v1 y v2 con renames/exposición/ocultación y path mapping.

### Evidencia

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/contexts/prompt_io_mapping.py`
- `backend/tests/test_negotiation_prompt_io_mapping.py`
- `backend/tests/test_negotiation_prompt_io_mapping_v2.py`
- `backend/tests/test_sala_reuniones_prompt_io_mapping.py`

---

## 6) Nodos actuales y contratos

## 6.1 Memory node

### Hechos observados

- Entrada incluye: user turn, recent dialogue, memory_working, scene state, episodic corta.
- Salida: `episodic_append`, `working_memory_new`, `negotiation_state`.

### Evidencia

- `backend/negociacion/nodes/memory_node.py`
- `backend/negociacion/contexts/*/prompts/summarizer_prompt.txt`

## 6.2 Phase classifier

### Hechos observados

- Entrada contextualiza fase previa + historial reciente + card de clasificación.
- Salida mínima: `current_phase`.

### Evidencia

- `backend/negociacion/nodes/phase_classifier_node.py`
- `backend/negociacion/orchestration/flow_config.py`

## 6.3 Planner

### Hechos observados

- Nodo táctico que decide status/goal/limits/memory_targets.
- Usa persona policy + brief + fase + memoria y estado.

### Evidencia

- `backend/negociacion/nodes/planner_node.py`
- `backend/negociacion/contexts/*/prompts/planner_prompt.txt`

## 6.4 Executor

### Hechos observados

- Produce respuesta final natural respetando planner limits.
- Se modela explícitamente como “no replanificar”.

### Evidencia

- `backend/negociacion/nodes/executor_node.py`
- `backend/negociacion/contexts/*/prompts/executor_prompt.txt`

---

## 7) Estado canónico y persistencia

### Hechos observados

- `CanonicalState` contiene sesión, hilo OpenAI, persona, brief, memoria, estado negociador, estado planner, escena, UI y trace state.
- Persistencia runtime:
  - `world_state["negotiation_canonical"]`
  - `world_state["negotiation_canonical_recent_dialogue"]`
  - `world_state["negotiation_canonical_traces"]`
- Se conserva también `conversation_id` / `previous_response_id` del threading.

### Evidencia

- `backend/negociacion/state/canonical_state.py`
- `backend/negociacion/orchestration/flow_config.py` (`StateRepository`)
- `backend/tests/test_railway_multiuser_readiness.py`

---

## 8) Memoria operativa actual (detalle solicitado)

### Hechos observados

1. **Recent dialogue trimming sí existe**:
   - se compacta con `_compact_recent(recent_dialogue, config.max_recent_messages)`.
2. **Memoria episódica no tiene trimming estructural explícito en runtime**:
   - se hace `extend(...)` de `episodic_append`.
3. **Summarization de turno actual sí existe**:
   - la hace el nodo `memory` vía `summarizer_prompt.txt` y produce `working_memory_new.last_turn_summary` y patch episódico.
4. **Compresión histórica diferida (old turns summary global) no aparece como subsistema explícito en esta ruta**.

### Evidencia

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/nodes/memory_node.py`
- `backend/negociacion/contexts/baseline_current/prompts/summarizer_prompt.txt`
- `backend/negociacion/contexts/sala_reuniones/prompts/summarizer_prompt.txt`

---

## 9) Presentation contextual

### Hechos observados

- Resolver mezcla defaults + overrides por contexto (`presentation/presentation_config.json`).
- Normaliza assets relativos a `/interfaz_usuario/context-assets/{context_id}/...`.
- `SessionBootstrapResponse` ya devuelve `presentation_config` para UI.

### Evidencia

- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/models.py`
- `backend/api/app.py` (serving de assets contextuales)

---

## 10) Tests relevantes (muestra no exhaustiva)

### Contexto y contratos

- `backend/tests/test_turn_context_contract.py`
- `backend/tests/test_context_contract_topdown_regression.py`
- `backend/tests/test_phase3_context_session_binding.py`
- `backend/tests/test_phase4_public_context_surface.py`
- `backend/tests/test_phase8_second_official_context.py`
- `backend/tests/test_phase8_second_official_context_e2e_http.py`

### Prompt IO mapping y assets

- `backend/tests/test_negotiation_prompt_io_mapping.py`
- `backend/tests/test_negotiation_prompt_io_mapping_v2.py`
- `backend/tests/test_sala_reuniones_prompt_io_mapping.py`
- `backend/tests/test_negotiation_context_assets_schema.py`
- `backend/tests/test_sala_reuniones_asset_shape_tolerance.py`

### Superficies y runtime

- `backend/tests/test_api_negociar_context_contract.py`
- `backend/tests/test_interfaz_usuario_turn_error_handling.py`
- `backend/tests/test_optimizador_turn_error_handling.py`
- `backend/tests/test_phase4_phase5_session_runtime.py`
- `backend/tests/test_phase6_phase7_session_lifecycle.py`

---

## 11) Conclusiones del mapeo

1. La base transversal (sesión, contexto, contrato, trazas, superficies) está madura y reusable.
2. El mayor acoplamiento a `negociacion` vive en:
   - naming (`negotiation_*`),
   - shape de estado canónico,
   - contratos de nodos de 4 etapas.
3. El cambio a 1 LLM online es viable, pero requiere una capa de abstracción de flujo para evitar duplicar superficies y tooling.
