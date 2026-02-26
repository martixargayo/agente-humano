# Implementation Plan — Phase System (planner → runtime → executor)

## 1) Alcance y no-alcance

### Qué cambia
- Sustitución de prompts activos de **planner** por los definidos en `docs/prompts/prod_planner_llm_v1.md`.
- Sustitución de prompts activos de **executor** por los definidos en `docs/prompts/prod_executor_llm_v2.md`.
- Implementación operativa del contrato de fases/topics documentado en:
  - `docs/prompts/phase_system_overview.md`
  - `docs/prompts/phase_clima_humano.md`
  - `docs/prompts/phase_descubrimiento_y_comprension.md`
  - `docs/prompts/phase_propuesta_creativa.md`
  - `docs/prompts/phase_concesiones_y_ajuste_final.md`
  - `docs/prompts/phase_formalizacion_del_acuerdo.md`

### Qué NO cambia
- **World judge**: no se modifica prompt ni comportamiento funcional (mantener contrato `judge_semantic_v1`).
- No se cambian los schemas de salida ya existentes:
  - `planner_semantic_v1` (`PlannerSemanticV1DecisionModel`)
  - `executor_v2` (normalización y contrato actual)
  - `judge_semantic_v1` (validación actual en world node)
- No se cambia la topología del grafo ni orden de nodos (`world -> planner -> executor`).

### Assumptions
- Modelos activos en config: planner/executor en `gpt-5-nano` (defaults actuales).
- Planner usa structured outputs (`with_structured_output(PlannerSemanticV1DecisionModel)`).
- Executor parsea JSON de texto y aplica normalización/guardrails runtime.
- Se permite transmitir tema por convención textual `TEMA: "..."` dentro de `next_move_hint` sin cambios de schema.

## 2) Inventario del estado actual del repo

### Dónde viven hoy los prompts activos
- Fuente principal de prompts versionados: `backend/prompts.py`.
- Planner consume prompts desde:
  - `backend/negotiation/repo_prompts.py` (reexport)
  - `backend/negotiation/phase_policy_planner.py` (`PLANNER_SEMANTIC_V1_SYSTEM_PROMPT`, `PLANNER_SEMANTIC_V1_USER_PROMPT`).
- World judge consume prompts desde:
  - `backend/negotiation/repo_prompts.py` (reexport de `WORLD_JUDGE_V3_*`)
  - `backend/negotiation/nodes/world_node.py`.
- Executor hoy **no** usa `backend/prompts.py`; usa:
  - `backend/negotiation/elementos/render/executor_prompts.py` (`EXECUTOR_V2_*`)
  - `backend/negotiation/executor/render_executor.py`.

### Cómo se inyecta el input actual
- Planner (`phase_policy_planner.py`) construye template con:
  - `user_message`, `assistant_last_message`, `recent_history_text`, `objective_summary`.
  - `full_profiles_block`, `memory_short`, `memory_long`.
  - `semantic_ledger_json`, `phase_map_json`, `advisor_recs_json`.
- Executor (`render_executor.py`) inyecta hoy:
  - `planner_semantic_output_json`, `semantic_ledger_json`, `advisor_recs_json`.
  - `user_message`, `last_counterparty_utterance`, `assistant_last_message`, `recent_history_text`.
  - `memory_short`, `memory_long`, `belief_json`, `world_json`, `phase_map_json`.

### Cómo se parsea y valida el output actual
- Planner:
  - Validación fuerte por Pydantic `PlannerSemanticV1DecisionModel`.
  - Structured output en `phase_policy_planner.py`.
- Executor:
  - Parse JSON best-effort (`safe_json_load`) + `normalize_executor_output`.
  - Post-validación de límites en `_enforce_executor_v2_contract` (word cap y max_questions).
  - Retry por longitud (`REINTENTO_BREVEDAD`) en `render_executor.py`.
  - Validator de contenido crítico existe en `backend/negotiation/validator.py` y `backend/negotiation/elementos/render/validator_rules.py`, pero no está cableado explícitamente en `executor_node.py`.
- World judge:
  - Parse JSON + comprobación `schema_version/topic_alignment` + normalización de ledger en `world_node.py`.

## 3) Mapa de cambios (diff conceptual)

### Planner
- Prompt SYSTEM/USER pasa a versión de `prod_planner_llm_v1.md`.
- Input esperado del planner incorpora explícitamente:
  - `prev_phase`, `allowed_next_phases`.
  - `style_id`, `max_words`, `max_questions`.
  - `SEMANTIC_LEDGER` en listas humanas (`lo_que_ya_se_toco`, `lo_que_ya_pregunte`, `lo_que_falta_pero_no_insistire`).
  - `PHASES_RESUMEN` (1 línea por fase oficial).
- `next_move_hint` incluye línea `TEMA: "<label exacto>"` (convención, sin tocar schema).

### Executor
- Prompt SYSTEM/USER pasa a versión de `prod_executor_llm_v2.md`.
- Input del executor deja de depender del mapa completo y recibe:
  - `PHASE_CARD_EXTENDIDA` **solo** de la fase seleccionada.
  - `SEMANTIC_LEDGER` humano (3 listas).
  - `TEMA_SELECCIONADO` (extraído de `next_move_hint` o campo runtime opcional).
- Se mantiene salida `executor_v2` actual (sin cambios de schema).

### Runtime wiring
- Agregar lookup explícito por `phase` para `PHASE_CARD_EXTENDIDA`.
- Inyección de una única card al template executor.
- Parser robusto de `TEMA: "..."` desde `next_move_hint`.

## 4) Plan de implementación paso a paso (muy concreto)

### 4.1 Sustitución prompts

**Archivo(s) a tocar (paths exactos)**
- `backend/prompts.py`.
- `backend/negotiation/elementos/render/executor_prompts.py`.
- `backend/negotiation/repo_prompts.py` (solo si se requieren nuevos nombres exportados).

**Qué modificar exactamente**
- Reemplazar `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT` y `PLANNER_SEMANTIC_V1_USER_PROMPT` con los bloques de `docs/prompts/prod_planner_llm_v1.md`.
- Reemplazar `EXECUTOR_V2_SYSTEM_PROMPT` y `EXECUTOR_V2_USER_PROMPT` con los bloques de `docs/prompts/prod_executor_llm_v2.md`.
- Confirmar world judge sin cambios funcionales (`WORLD_JUDGE_V3_*` intacto).

**Qué NO tocar**
- `backend/negotiation/elementos/strategy_definitions.py` (schema planner).
- Contrato de salida de `normalize_executor_output`.
- `backend/negotiation/nodes/world_node.py` (flujo judge).

**Cómo verificarlo**
- Revisar prompts renderizados en telemetry (`planner_input_prompt_rendered`, `judge_input_prompt_rendered`, `executor input_prompt_rendered`).
- Verificar presencia textual de secciones nuevas: `PHASE CONTROL`, `SEMANTIC_LEDGER`, `PHASE_CARD`.

### 4.2 Implementación “TEMA: …”

**Archivo(s) a tocar (paths exactos)**
- `backend/negotiation/phase_policy_planner.py`.
- `backend/negotiation/executor/render_executor.py`.
- Opcional helper: `backend/negotiation/context_utils.py`.

**Qué modificar exactamente**
- Planner: reforzar (prompt + post-check soft) que `next_move_hint` contenga `TEMA: "..."`.
- Runtime: implementar extractor robusto de tema desde `next_move_hint`.
  - Regex recomendada: `(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$`.
  - Fallback: aceptar línea `TEMA: ...` sin comillas.
- Persistir tema en estado (`state["topic_selected"]`) para trazabilidad/debug.

**Fallback si falta TEMA**
- Prioridad 1: topic default por fase (primer topic oficial de la fase).
- Prioridad 2: `topic_selected="sin_tema"` y continuar sin romper pipeline.
- Registrar flag en meta (`topic_selected_source=fallback`).

**Qué NO tocar**
- Schema `PlannerSemanticV1DecisionModel`.
- Campos de salida de planner.

**Cómo verificarlo**
- Tests unitarios del parser de `TEMA`.
- Traza de un turno donde planner devuelve tema correcto y executor lo recibe.

### 4.3 Lookup PHASE_CARD_EXTENDIDA

**Archivo(s) a tocar (paths exactos)**
- `backend/negotiation/phase_map.py` (si se reusa estructura actual) **o** nuevo módulo recomendado `backend/negotiation/phase_cards.py`.
- `backend/negotiation/executor/render_executor.py`.
- `backend/negotiation/nodes/executor_node.py` (solo para asegurar inyección limpia en estado si hace falta).

**Qué modificar exactamente**
- Crear catálogo `PHASE_CARD_EXTENDIDA` indexado por IDs oficiales:
  - `clima_humano`
  - `descubrimiento_y_comprension`
  - `propuesta_creativa`
  - `concesiones_y_ajuste_final`
  - `formalizacion_del_acuerdo`
- Implementar función:
  - `get_phase_card_extended(phase_id: str) -> dict` con validación y fallback seguro.
- En runtime, resolver card desde `planner_semantic_output.phase` e inyectar **solo esa** card en el prompt del executor.

**Qué NO tocar**
- No enviar mapa completo de cards al executor.
- No introducir nuevos campos en schema `executor_v2`.

**Cómo verificarlo**
- Assert de que el prompt executor contiene una sola card.
- Assert de error/fallback controlado cuando `phase_id` no existe.

### 4.4 Validaciones / guardrails externos

**Archivo(s) a tocar (paths exactos)**
- `backend/negotiation/executor/render_executor.py`.
- `backend/negotiation/validator.py`.
- `backend/negotiation/elementos/render/validator_rules.py`.
- (si aplica) `backend/negotiation/nodes/executor_node.py` para cablear validator.

**Qué modificar exactamente**
- Mantener y reforzar validación de `max_words` y `max_questions`.
- Añadir patrones de canal solo texto (prohibidos: muéstrame/enséñame/envíame/adjunta/pásame/tráeme).
- Integrar `validate_and_repair` al flujo executor (hoy no se observa conexión directa en `executor_node.py`).
- Definir retry/repair corto:
  - 1 retry con `retry_hint` específico por violación.
  - Si persiste, fallback seguro.

**Qué NO tocar**
- No cambiar estructura de salida `executor_v2`.

**Cómo verificarlo**
- Casos de prueba con texto prohibido y confirmación de reparación.
- Comprobación de recorte/normalización final consistente.

### 4.5 Migración sin downtime

**Archivo(s) a tocar (paths exactos)**
- `backend/negotiation/config/models.py` (si se quiere flag en config central) **o** lectura de env en módulos de planner/executor.
- `backend/negotiation/phase_policy_planner.py`.
- `backend/negotiation/executor/render_executor.py`.

**Qué modificar exactamente**
- Introducir feature flag de prompt/wiring, por ejemplo:
  - `NEGOTIATION_PHASE_SYSTEM_V2_ENABLED=0|1`.
- Rollout gradual:
  - sombra interna (log-only) -> 10% -> 50% -> 100%.
- Métricas a observar:
  - tasa de parse JSON planner/executor.
  - tasa de fallback y retries.
  - violaciones de canal solo texto.
  - `ledger_mismatch_detected` y coherencia phase/topic.

**Qué NO tocar**
- Sin switch de world judge.

**Cómo verificarlo**
- Dashboard/telemetry por cohortes de flag.
- Rollback inmediato al prompt anterior vía flag.

## 5) Checklist de compatibilidad y riesgos

### Riesgos principales
- `phase` fuera de IDs oficiales.
- Labels de topic no exactos (rompe parseo/consistencia).
- Parser de `TEMA` frágil ante variaciones de formato.
- Desalineación planner->executor si no se inyecta card única.
- Prompt drift en executor que incumpla canal solo texto.

### Mitigaciones
- Asserts fuertes de phase ID y fallback controlado.
- Catálogo central de topics por fase + validación exacta de label.
- Parser regex + fallback robusto + logs de observabilidad.
- Test de prompt render que verifique solo una `PHASE_CARD_EXTENDIDA`.
- Validator externo + retry corto + fallback seguro.

## 6) Testing plan (obligatorio)

### Unit tests
- Parse de `TEMA` desde `next_move_hint` (comillas dobles, comillas tipográficas, sin comillas, faltante).
- `get_phase_card_extended(phase_id)`:
  - 5 fases válidas.
  - fase inválida con fallback.
- Validación de schema planner (`planner_semantic_v1`) no alterado.
- Guardrails executor:
  - max_words/max_questions.
  - verbos prohibidos de canal no textual.

### Integration tests (mínimo 10 casos)
- 2 casos por fase oficial (total 10):
  - planner emite phase válida + `TEMA` exacto.
  - runtime inyecta card correcta.
  - executor responde dentro de límites y sin drift.
- Incluir casos con pregunta directa del vendedor (HUMAN-FIRST).
- Incluir caso con `TEMA` faltante para validar fallback.

### Replay suite
- Reusar tooling existente en repo:
  - `scripts/replay_behavior_suite.py`
  - `scripts/manual_mustang_qa_runner.py`
- Ejecutar replays históricos pre/post y comparar:
  - cumplimiento JSON.
  - cumplimiento de constraints.
  - reducción de repreguntas/repetición.

## 7) Definition of Done
- Planner y executor ejecutan con prompts nuevos en producción detrás de flag.
- World judge permanece sin cambios funcionales ni de contrato.
- `phase` siempre pertenece al set oficial.
- `next_move_hint` incluye `TEMA` válido o fallback registrado.
- Runtime inyecta una sola `PHASE_CARD_EXTENDIDA` por turno.
- Executor cumple max_words/max_questions y canal solo texto en tests.
- Suite unitaria + integración + replay en verde.
- Observabilidad habilitada (topic source, fallback reason, phase-card lookup status).
