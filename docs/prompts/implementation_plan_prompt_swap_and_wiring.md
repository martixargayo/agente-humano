# Implementation Plan — Prompt Swap + Wiring

## A) Alcance / no-alcance

### Alcance
- Swap de prompts activos de **planner** a los definidos en `docs/prompts/prod_planner_llm_v1.md`.
- Swap de prompts activos de **executor** a los definidos en `docs/prompts/prod_executor_llm_v2.md`.
- Alineación de wiring planner→runtime→executor para:
  - `TEMA: "<label exacto>"` dentro de `next_move_hint`.
  - lookup e inyección de **una sola** `PHASE_CARD_EXTENDIDA` por turno.
- Alineación del consumo de memoria a `SEMANTIC_LEDGER` en texto humano breve (sin suposiciones de tags).
- Mantener compatibilidad con schemas actuales: `planner_semantic_v1`, `executor_v2`, `judge_semantic_v1`.

### No-alcance
- No hay cambio de schema de salida en world_judge/planner/executor.
- No se cambia la topología del grafo (`world -> planner -> executor`).
- No se modifica el contrato base de `world_judge` (`judge_semantic_v1`), solo su representación de items en texto humano breve ya documentada.
- No se implementa código en este entregable (plan solamente).

---

## B) Inventario del estado actual (paths exactos)

### Prompts activos y puntos de render
- **Planner prompt source**: `backend/prompts.py` (`PLANNER_SEMANTIC_V1_SYSTEM_PROMPT`, `PLANNER_SEMANTIC_V1_USER_PROMPT`).
- **World judge prompt source**: `backend/prompts.py` (`WORLD_JUDGE_V3_SYSTEM_PROMPT`, `WORLD_JUDGE_V3_USER_PROMPT`).
- **Reexport de prompts**: `backend/negotiation/repo_prompts.py`.
- **Planner render/invoke**: `backend/negotiation/phase_policy_planner.py`.
- **World judge render/invoke**: `backend/negotiation/nodes/world_node.py`.
- **Executor prompt source activo**: `backend/negotiation/elementos/render/executor_prompts.py`.
- **Executor render/invoke**: `backend/negotiation/executor/render_executor.py` (llama `deps.execute` con prompt renderizado).

### Construcción de input actual
- **Planner input actual** (en `phase_policy_planner.py`):
  - `user_message`, `assistant_last_message`, `recent_history_text`, `objective_summary`.
  - `full_profiles_block`, `memory_short`, `memory_long`.
  - `semantic_ledger_json`, `phase_map_json`, `advisor_recs_json`.
- **Executor input actual** (en `render_executor.py`):
  - `planner_semantic_output_json`, `semantic_ledger_json`, `advisor_recs_json`.
  - `last_counterparty_utterance`, `user_message`, `assistant_last_message`, `recent_history_text`.
  - `memory_short`, `memory_long`, `belief_json`, `world_json`, `retry_hint`, `phase_map_json`.

### Parse/normalización de semantic_ledger
- `backend/negotiation/semantic_ledger_utils.py`:
  - `normalize_semantic_ledger()` → listas de strings, trim + max 180 chars + tope 6.
  - `build_effective_semantic_ledger()` fusiona persistido + judge.
- `backend/negotiation/nodes/world_node.py`:
  - `_normalize_semantic_ledger()` con misma forma de listas de strings.
- `backend/negotiation/progress_updater.py`:
  - persiste `semantic_ledger` con misma estructura 3 listas y saneo.

### Lugares con supuestos de tags / UPPER_SNAKE_CASE
- No hay parser técnico que requiera UPPER_SNAKE_CASE en runtime (se operan listas de strings libres).
- El riesgo está en texto de prompt legacy y en docs, no en schema/código de normalización.

---

## C) Diff conceptual (planner/executor/judge + wiring)

### Judge
- **No cambia schema ni estructura** (`judge_semantic_v1`).
- Se mantiene la misma tríada de listas:
  - `lo_que_ya_se_toco`
  - `lo_que_ya_pregunte`
  - `lo_que_falta_pero_no_insistire`
- Cambio conceptual ya documentado: items en **texto humano breve** (idea-level), no tags.

### Planner
- Prompt se alinea con `prod_planner_llm_v1.md`:
  - control explícito de fase por `allowed_next_phases` + `prev_phase`.
  - `style` debe igualar `style_id`.
  - `next_move_hint` ejecutable con `RESPUESTA/MOVIMIENTO/PREGUNTA`.
  - inclusión de `TEMA: "<label exacto>"` dentro de `next_move_hint` (sin schema nuevo).
- Input se simplifica y orienta a contrato:
  - `SEMANTIC_LEDGER` humano + contexto compacto + constraints.

### Executor
- Prompt se alinea con `prod_executor_llm_v2.md`:
  - consume `planner_semantic_output` + `SEMANTIC_LEDGER` humano.
  - consume `PHASE_CARD` de **solo** la fase elegida.
  - usa `TEMA_SELECCIONADO` como ancla de ejecución (movimiento sin interrogatorio).
- Mantiene salida `executor_v2` actual.

### Wiring
- Runtime extrae `phase` y `next_move_hint` de planner.
- Runtime parsea `TEMA` desde `next_move_hint` (regex robusta + fallback).
- Runtime hace lookup `PHASE_CARD_EXTENDIDA` por `phase` e inyecta solo esa card al executor.

---

## D) Plan paso a paso (tasks concretas + archivos a tocar)

### D.1 Prompt swap planner/judge/executor
1. Actualizar planner prompt activo en `backend/prompts.py` con bloques de `docs/prompts/prod_planner_llm_v1.md`.
2. Mantener world_judge en `backend/prompts.py`/`world_node.py` con contrato actual (sin schema changes).
3. Actualizar executor prompt activo en `backend/negotiation/elementos/render/executor_prompts.py` con bloques de `docs/prompts/prod_executor_llm_v2.md`.

### D.2 Wiring de `TEMA`
4. Añadir helper de parseo de `TEMA` en runtime (recomendado en `backend/negotiation/executor/render_executor.py` o util compartido):
   - regex primaria: `(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$`
   - fallback secundario: `(?im)^\s*TEMA\s*:\s*(.+?)\s*$`
5. Persistir en estado/meta:
   - `topic_selected`
   - `topic_selected_source` (`hint_regex|hint_fallback|phase_default|none`).
6. Fallback si falta `TEMA`:
   - default por fase (primer label de `TOPICS_POR_FASE` de esa fase), o
   - `sin_tema` controlado si no hay default disponible.

### D.3 Catálogo + lookup PHASE_CARD_EXTENDIDA
7. Crear catálogo central de cards extendidas (recomendado nuevo archivo `backend/negotiation/phase_cards_extended.py` o ampliar `phase_map.py` sin mezclar mapas viejos).
8. Implementar `get_phase_card_extended(phase_id: str) -> dict` con validación de IDs oficiales.
9. En `render_executor.py`, inyectar al prompt solo:
   - `phase`
   - `do`
   - `avoid`
   - `question_policy`
   - `topic_selected`.

### D.4 Limpieza/simplificación del input executor
10. Reducir payload del executor a lo esencial del contrato nuevo.
11. Campos candidatos a retirar del prompt del executor (mantener opcionales bajo flag durante migración):
   - `phase_map_json` completo (reemplazado por card única).
   - `advisor_recs_json` (si no aporta señal efectiva en ejecución final).
   - `world_json` como input de decisión (dejar solo compat temporal si necesario).

### D.5 Telemetría, guardrails y rollout
12. Añadir métricas y trazas nuevas:
   - `topic_selected`
   - `topic_selected_source`
   - `phase_card_lookup_status` (`ok|fallback|missing`).
   - `executor_retry_count`.
   - `text_only_violations_count`.
13. Cablear validación crítica al flujo executor si no está activa (vía `validate_and_repair`).
14. Activar rollout por flag (p.ej. `NEGOTIATION_PROMPT_SWAP_V2=0|1`) con rollback inmediato.

### Tabla: Archivos a tocar

| Archivo | Cambio | Riesgo | Test asociado |
|---|---|---|---|
| `backend/prompts.py` | Swap prompt planner; conservar world_judge contract | Drift de instrucciones vs runtime inputs | Snapshot de prompt render planner/judge |
| `backend/negotiation/repo_prompts.py` | Ajustar reexports si cambian nombres | Import break | Test de import y arranque |
| `backend/negotiation/phase_policy_planner.py` | Ajustar template/input planner + asegurar `TEMA` en hint | Planner no emite `TEMA` | Unit parse `next_move_hint`; integration phase cases |
| `backend/negotiation/elementos/render/executor_prompts.py` | Prompt executor nuevo con PHASE_CARD única | Prompt incompat con payload actual | Snapshot prompt executor |
| `backend/negotiation/executor/render_executor.py` | Parse `TEMA`, lookup card, input mínimo, telemetry | Parser frágil, card missing | Unit regex + integration 5 fases |
| `backend/negotiation/phase_map.py` o `backend/negotiation/phase_cards_extended.py` | Catálogo y `get_phase_card_extended` | IDs mismatch | Unit valid IDs + fallback |
| `backend/negotiation/validator.py` | Cablear repair/retry en flujo real | Overblocking respuestas | Unit guardrails + golden cases |
| `backend/negotiation/elementos/render/validator_rules.py` | Regla “solo texto” (verbos prohibidos) | Falsos positivos | Unit patrones positivos/negativos |
| `backend/negotiation/nodes/executor_node.py` | Pasar/registrar metadatos topic/card | Estado inconsistente | Integration e2e planner→executor |
| `backend/tests/test_semantic_runtime_v1.py` | Nuevos tests de tema/card/wiring | Cobertura incompleta | CI unit/integration |

---

## E) Validaciones y guardrails (qué checks añadir o cablear)

1. **Schema invariants**
- Planner: mantener `PlannerSemanticV1DecisionModel` (`planner_semantic_v1`).
- Executor: mantener contrato `executor_v2` (`normalize_executor_output` + `_enforce_executor_v2_contract`).
- Judge: mantener `judge_semantic_v1`.

2. **Guardrails de canal solo texto**
- Reglas explícitas para bloquear verbos de acción física/no textual:
  - `muéstrame`, `enséñame`, `envíame`, `adjunta`, `pásame`, `tráeme`.
- Integrar en `validator_rules.py` y aplicar en flujo executor (retry corto + fallback seguro).

3. **Checks de fase/topic**
- `phase` ∈ {`clima_humano`, `descubrimiento_y_comprension`, `propuesta_creativa`, `concesiones_y_ajuste_final`, `formalizacion_del_acuerdo`}.
- `topic_selected` debe existir en catálogo de `TOPICS_POR_FASE` para la fase activa.

4. **Compatibilidad ledger humano**
- Mantener normalizadores actuales (listas de strings, dedupe, trim, límite 6).
- Añadir assertion de tipo/lista (no formato UPPER_SNAKE_CASE).
- Confirmar que planner/executor consumen semantic_ledger como texto libre sin regex de tags.

---

## F) Testing plan (unit + integration + replay)

### Unit tests (mínimos)
1. Parser `TEMA`:
- con comillas dobles
- con comillas tipográficas
- sin comillas
- línea faltante
- múltiples líneas `TEMA` (usar la última o primera por regla explícita)

2. `get_phase_card_extended`:
- 5 fases válidas
- fase inválida -> fallback + status

3. Ledger humano:
- `normalize_semantic_ledger` conserva strings humanas y límites.
- no requiere UPPER_SNAKE_CASE para pasar.

4. Guardrails executor:
- max_words
- max_questions
- detección de verbos prohibidos en canal texto

### Integration tests (mínimo 10)
- 2 escenarios por fase oficial (10 total):
  - planner emite phase válida.
  - planner emite `TEMA` válido.
  - runtime inyecta card correcta y única.
  - executor responde en `executor_v2` válido, sin violar límites.
- casos adicionales:
  - `TEMA` faltante (fallback por fase).
  - pregunta directa del vendedor (HUMAN-FIRST).

### Replay
- Reusar scripts existentes:
  - `scripts/replay_behavior_suite.py`
  - `scripts/manual_mustang_qa_runner.py`
- Comparar pre/post:
  - parse success
  - retries
  - violaciones de canal
  - coherencia fase/topic

---

## G) Riesgos + mitigaciones + rollback (flag)

### Riesgos
- Fase inválida por desalineación planner/runtime.
- `TEMA` no parseable por variaciones de formato.
- Lookup de card ausente o mal indexado.
- Prompt executor sobrecargado y caída de calidad/obediencia.
- Regla “solo texto” demasiado estricta (falsos positivos).

### Mitigaciones
- Validación hard de phase ID + fallback a `clima_humano`.
- Parser con doble regex + fallback de topic por fase.
- Catálogo central tipado con tests unitarios.
- Reducir payload del executor (single phase card) para saliencia.
- Retry corto y mensaje de reparación dirigido por violación.

### Rollback
- Feature flag global para prompt swap/wiring (`NEGOTIATION_PROMPT_SWAP_V2`).
- Plan de rollout:
  - 0% (shadow logging)
  - 10%
  - 50%
  - 100%
- Rollback inmediato al estado anterior desactivando flag.

---

## H) Checklist final — Definition of Done

- [ ] Prompts activos de planner/executor actualizados según docs `prod_*`.
- [ ] World_judge mantiene `judge_semantic_v1` sin cambios de schema.
- [ ] `next_move_hint` incluye `TEMA` o fallback registrado.
- [ ] Runtime extrae `TEMA` (regex+fallback) y lo pasa al executor.
- [ ] Runtime inyecta **solo una** `PHASE_CARD_EXTENDIDA` por turno.
- [ ] `SEMANTIC_LEDGER` humano fluye end-to-end sin supuestos de tags.
- [ ] Guardrails de canal solo texto cableados al flujo executor.
- [ ] Métricas nuevas activas: `topic_selected_source`, `phase_card_lookup_status`, retries, violaciones solo texto.
- [ ] Unit tests + integration tests + replay plan ejecutables y en verde.
- [ ] Rollout con flag + procedimiento de rollback documentado.
