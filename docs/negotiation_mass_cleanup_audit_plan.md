# Auditoría EXTREMADAMENTE estricta — dead code / dead schema / dead prompts (negociación)

> **Fase actual:** solo auditoría + plan por PRs. **Sin cambios runtime**.

## 0) Evidencia ejecutada (comandos exactos + resumen)

### Comando A (runtime pipeline + updaters + trace)
```bash
rg -n "run_negotiation_agent|negotiation_graph|phase_policy_planner|progress_updater|update_world_state|update_belief_state|build_trace_event" backend
```
**Resumen objetivo:**
- Entrypoint negociación: `backend/app.py:262-277` (`POST /negociar` -> `run_negotiation_agent`).
- Builder de eventos LiveTrace: `backend/app.py:308`, `backend/negotiation/telemetry/live_trace.py:43`.
- Updaters core presentes y conectados en grafo (`negotiation_graph.py` + `nodes/*`).

### Comando B (open buckets vs legacy ramas)
```bash
rg -n "world_buckets|belief_buckets|negotiation_v2|universal_v2|world_observations|world_derived|open_claims" backend/negotiation backend/app.py backend/tests
```
**Resumen objetivo:**
- `world_buckets` / `belief_buckets` se escriben y leen en nodos, gating y telemetry.
- Legacy (`universal_domain`, `negotiation`, `universal_state`, `open_claims`, `world_observations*`, `world_derived`) sigue presente en normalización y/o señales auxiliares.
- `universal_v2` y `negotiation_v2` tienen lectores activos (`phase_state_updater.py`).

### Comando C (confirmación de `backend/negotiation/nodes/`)
```bash
rg -n "backend/negotiation/nodes/"
```
**Resumen objetivo:**
- Referencias en tests/docs.
- Uso runtime real confirmado por imports + `workflow.add_node(...)` en `negotiation_graph.py`.

### Comando D (desde dónde se llama cada nodo/updater)
```bash
for sym in world_updater_node belief_updater_node policy_progress_node phase_policy_planner_node progress_updater_node executor_node update_world_state update_belief_state update_progress_state plan_phase_policy; do
  rg -n "$sym" backend/negotiation backend/app.py backend/tests | head -n 40
done
```
**Resumen objetivo:**
- Nodos del grafo están conectados al runtime.
- `update_world_state`, `update_belief_state`, `update_progress_state` tienen llamadas runtime + tests.

---

### 0.1 Extractos literales de salida (obligatorios)

#### Extracto Comando A
```text
backend/app.py:277:        reply, _ = run_negotiation_agent(state, payload.message)
backend/app.py:308:                event = build_trace_event(
backend/negotiation/negotiation_graph.py:399:workflow.add_node("phase_policy_planner", phase_policy_planner_node)
backend/negotiation/negotiation_graph.py:400:workflow.add_node("progress_updater", progress_updater_node)
backend/negotiation/negotiation_graph.py:419:def run_negotiation_agent(
backend/negotiation/nodes/world_node.py:276:        world_state, extractor_meta = update_world_state(
backend/negotiation/nodes/belief_node.py:54:        belief_state, belief_meta = deps.update_belief_state(
backend/negotiation/telemetry/live_trace.py:43:def build_trace_event(
```

#### Extracto Comando B
```text
backend/negotiation/schemas.py:631:        "world_buckets": {
backend/negotiation/schemas.py:641:        "open_claims": [],
backend/negotiation/schemas.py:643:        "world_observations": {
backend/negotiation/schemas.py:647:        "world_observations_v2": {
backend/negotiation/schemas.py:655:        "world_derived": {"fields": {}},
backend/negotiation/phase_state_updater.py:60:    clarity_vague = bool(_nested_get(world_state, "universal_v2", "clarity", "is_vague"))
backend/negotiation/phase_state_updater.py:67:    interests_n = _len_value(_nested_get(world_state, "negotiation_v2", "interests"))
backend/negotiation/belief_state_updater.py:116:    open_claims = (world_state or {}).get("open_claims", []) if isinstance(world_state, dict) else []
backend/negotiation/validation.py:949:    observations = raw.get("world_observations", {})
backend/negotiation/validation.py:1005:    derived = raw.get("world_derived", {})
```

#### Extracto Comando C + confirmación de uso real en runtime
```bash
rg -n "backend/negotiation/nodes/"
rg -n "from \.nodes\.|workflow.add_node\(|workflow.add_edge\(" backend/negotiation/negotiation_graph.py
```
```text
backend/negotiation/negotiation_graph.py:91:from .nodes.world_node import world_updater_node
backend/negotiation/negotiation_graph.py:96:from .nodes.executor_node import executor_node
backend/negotiation/negotiation_graph.py:396:workflow.add_node("world_updater", world_updater_node)
backend/negotiation/negotiation_graph.py:401:workflow.add_node("executor", executor_node)
backend/negotiation/negotiation_graph.py:405:workflow.add_edge("world_updater", "belief_updater")
backend/negotiation/negotiation_graph.py:409:workflow.add_edge("progress_updater", "executor")
```


## 1) Mapa de ejecución real (runtime path)

## 1.1 Entry points reales

- `POST /negociar` (`backend/app.py:262`) llama `run_negotiation_agent` (`backend/app.py:277`).
- `run_negotiation_agent` (`backend/negotiation/negotiation_graph.py:419`) prepara estado, invoca LangGraph y persiste respuesta/traza.
- LiveTrace SSE llama `build_trace_event(...)` (`backend/app.py:308`, `backend/negotiation/telemetry/live_trace.py:43`).

## 1.2 Orden exacto de nodos en grafo activo

Definido en `backend/negotiation/negotiation_graph.py`:
- Nodos (`396-401`):
  1. `world_updater`
  2. `belief_updater`
  3. `policy_progress`
  4. `phase_policy_planner`
  5. `progress_updater`
  6. `executor`
- Edges (`403-411`):
  `START -> world_updater -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor -> END`

## 1.3 Qué produce cada nodo (keys escritas)

- `world_updater_node` (`nodes/world_node.py:218-343`):
  - escribe `state.world_state`, `state.world_diff`, `state.extractor_meta`, `state.policy_plan_judgement`, `state.world_debug`, `state.progress_state.gate_state`.
- `belief_updater_node` (`nodes/belief_node.py:17-129`):
  - escribe `state.belief_state`, `state.belief_update_meta`, `state.belief_debug`, `state.progress_state.gate_state`.
- `policy_progress_node` (`nodes/policy_progress_node.py:7-43`):
  - escribe `progress_state.policy_state`, `progress_state.advance_step`, `progress_state.last_judgement_status`, `state.policy_hint`, `state.policy_meta`.
- `phase_policy_planner_node` (`nodes/planner_node.py:105-307`):
  - escribe `state.policy_decision`, `state.phase_effective`, `state.executor_instruction`, `state.allowed_policy_ids`, `state.planner_meta`, `state.planner_debug`, `progress_state.active_plan*`.
- `progress_updater_node` (`nodes/progress_node.py:20-87`):
  - escribe `state.progress_state`, `state.progress_debug`, `progress_state.render_constraints_struct`.
- `executor_node` (`nodes/executor_node.py:65-175`):
  - escribe `state.response`, `state.assistant_message`, `state.executor_output`, `state.executed_policy`, `state.executor_render_meta`, `state.executor_validator_meta`.

## 1.4 ¿Hay segundo pipeline?

Sí, hay **otro endpoint** (`POST /chat`) que usa `run_agent` (pipeline no-negociación) en `backend/app.py:244-255`.

Para negociación específicamente (`/negociar`), no se detectó segundo pipeline paralelo de ejecución de respuesta final: el camino activo es el grafo anterior.

---

## 2) Matriz Read/Write por key_path (estricta)

> Convención:
> - Writer/Reader = `función (archivo:línea)`.
> - “runtime-critical” = si participa en decisión/respuesta de `/negociar`.
> - “borrar ya” solo si no hay readers runtime o hay sustituto claro.

## 2.1 `world_state`

| key_path | WRITERS (func+archivo+línea) | READERS (func+archivo+línea) | runtime-critical | ¿borrar ya? | migración requerida |
|---|---|---|---|---|---|
| `world_state.world_buckets.*` | `ensure_world_buckets`, `merge_world_buckets_append_mostly`, `update_world_state` (`world_state_updater.py:162-208,315-397`) | `belief_updater_node` (`nodes/belief_node.py:26-27`), `world_updater_node` debug diff (`nodes/world_node.py:308-320`) | Sí | No | Es core target.
| `world_state.world_state_meta.*` | `update_world_state` (`world_state_updater.py:333-336,379-384,400-403`) + `normalize_world_state` (`validation.py:1015-1049`) | trace/event export (`negotiation_graph.py:729-734`, `live_trace.py` varios) | Sí | No | Mantener mínimo (`turn_idx`, `updated_fields`, `extractor_failed`, `unknown_claims`).
| `world_state.policy_plan_judgement` (en state global) | `world_updater_node` (`nodes/world_node.py:295-306`) | `policy_progress_node` (`nodes/policy_progress_node.py:9-33`) + trace (`negotiation_graph.py:633`) | Sí | No | Core planner-progress handshake.
| `world_state.universal_domain.*` | `update_world_state` patch legacy (`world_state_updater.py:362-369`), `normalize_world_state` (`validation.py:821-834`) | `diff_world_state` (`world_state_updater.py:420-431`), `has_belief_evidence_delta` (`belief_state_updater.py:67-79`) | Parcial (legacy) | No (aún) | PR2: contadores + stop-read con fallback bucketizado.
| `world_state.negotiation.*` | `update_world_state` patch legacy (`world_state_updater.py:363,370`), `normalize_world_state` (`validation.py:822,843-932`) | `mode_inference.compute_mode_score` (`mode_inference.py:6-14`), `world_judge_llm payload` (`nodes/world_node.py:179`), `belief_state_updater` micro patch (`belief_state_updater.py:114-131`) | Sí (hoy) | No | Migrar a señales desde `world_buckets` (PR2) antes de borrar.
| `world_state.universal_state.*` | `update_world_state` merge (`world_state_updater.py:364,371-374`), `normalize_world_state` (`validation.py:1052`) | `world_judge_llm payload` (`nodes/world_node.py:180`), `world_updater_node` fingerprint (`nodes/world_node.py:332-334`), `belief_state_updater` (`belief_state_updater.py:115-123`) | Sí (hoy) | No | Definir equivalentes en buckets/meta y mover fingerprint gate.
| `world_state.universal_v2.*` | `normalize_world_state_v2` (`validation.py:604-656`) | `phase_state_updater._gate_effective_phase` (`phase_state_updater.py:60-67`) + `belief_state_updater._interaction_strong` (`belief_state_updater.py:100-108`) | Sí | No | PR2: o mantener mínimos, o mover a buckets planner-signals.
| `world_state.negotiation_v2.*` | `normalize_world_state_v2` (`validation.py:657+`) | `phase_state_updater._gate_effective_phase` (`phase_state_updater.py:67-71`) | Sí | No | Igual que arriba.
| `world_state.open_claims` | `update_world_state` (`world_state_updater.py:365,375-376`), `normalize_world_state` (`validation.py:1053`) | `belief_state_updater._micro_negotiation_patch_from_world` (`belief_state_updater.py:116,124`) | Parcial | No (aún) | Medir reader real por contador; migrar señales a buckets.claims.
| `world_state.evidence_items` | `normalize_world_state` (`validation.py:945`) | no reader runtime crítico identificado (solo normalización) | No (aparente) | No directo | PR1 instrumentación `read counter`; borrar PR3 si 0.
| `world_state.world_observations` | `normalize_world_state` (`validation.py:953,963`) | no reader runtime crítico identificado | No (aparente) | No directo | Igual: contador y validación ON/OFF.
| `world_state.world_observations_v2` | `normalize_world_state` (`validation.py:969-999`) | `top_evidence_v2` (`telemetry/trace.py:46-47`) | Solo telemetry | Deprecar primero | Pasar top-evidence a buckets/meta.
| `world_state.world_derived` | `normalize_world_state` (`validation.py:1005-1010`) | no reader runtime crítico identificado | No (aparente) | No directo | Instrumentar + eliminar si 0.

## 2.2 `belief_state`

| key_path | WRITERS | READERS | runtime-critical | ¿borrar ya? | migración |
|---|---|---|---|---|---|
| `belief_state.belief_buckets.*` | `update_belief_state` (`belief_state_updater.py:496-503`), merge helper (`191-213`) | `belief_updater_node` debug (`nodes/belief_node.py:86-100`), trace compact (`negotiation_graph.py:139-154`) | Sí | No | Core target.
| `belief_state.universal.dynamics.*` | `merge_belief_universal` (`belief_state_updater.py:340-352`), normalize (`validation.py:1086+`) | `phase_state_updater._compute_recovery_mode` (`phase_state_updater.py:37`) + debug planner_relevant (`nodes/belief_node.py:113-124`) | Sí | No | Mantener mínimo o migrar a buckets/meta planner-signals.
| `belief_state.universal.behavior_guidance.*` | `merge_belief_universal` + governor (`belief_state_updater.py:149-154,508-512`) | `phase_state_updater._compute_recovery_mode` (`phase_state_updater.py:38`) + debug (`nodes/belief_node.py:114-124`) | Sí | No | Igual arriba.
| `belief_state.negotiation.*` | `update_belief_state` (`belief_state_updater.py:476-485,494-495`) | no reader crítico directo en nodos (más bien estado heredado) | Parcial/legacy | No directo | PR2 medir accesos; mover lo útil a buckets.

## 2.3 `progress_state`

| key_path | WRITERS | READERS | runtime-critical | ¿borrar ya? | migración |
|---|---|---|---|---|---|
| `progress_state.gate_state.*` | `world_updater_node` (`nodes/world_node.py:223-342`), `belief_updater_node` (`nodes/belief_node.py:23-25,85`) | gates world/belief (`nodes/world_node.py:247-261`, `nodes/belief_node.py:30-40`) | Sí | No | Core control-plane.
| `progress_state.policy_state.planner_request` | `policy_progress.update_policy_state` (`policy_progress.py:59-72`) | `phase_policy_planner_node` (`nodes/planner_node.py:114-116`) | Sí | No | Core.
| `progress_state.advance_step` | `policy_progress.py:57` | `phase_policy_planner_node` (`nodes/planner_node.py:117`) | Sí | No | Core.
| `progress_state.active_plan` / `active_plan_status` | `phase_policy_planner_node` (`nodes/planner_node.py:266-271`) | `world_updater_node` world_judge input (`nodes/world_node.py:294-297`), `progress_updater.py:80-89`, `executor_instruction` derivación | Sí | No | Core.
| `progress_state.loop_flags` | `update_progress_state` (`progress_updater.py:78-113`) | `phase_state_updater._compute_recovery_mode` (`phase_state_updater.py:39-43`) | Sí | No | Core anti-loop.
| `progress_state.render_state` | defaults + preset apply en graph (`negotiation_graph.py:488-507`) | `executor_node` (`nodes/executor_node.py:80-97`) | Sí | No | Core render.
| `progress_state.render_constraints_struct` | `progress_updater_node` (`nodes/progress_node.py:37-47`) | `executor_node` (`nodes/executor_node.py:89-97`) | Sí | No | Core render safety.

## 2.4 `policy_state` / `phase_state` (dentro de progress)

| key_path | WRITERS | READERS | runtime-critical | ¿borrar ya? | migración |
|---|---|---|---|---|---|
| `policy_state.status`/`policy_state.last_turn` | `policy_progress.py:37-43,66-73` | planner/progress (indirecto por `planner_request`) | Sí | No | Core.
| `phase_state.phase_effective` | `postprocess_phase_candidate` (`phase_state_updater.py:127-183`) | planner debug + trace + executor strategy context | Sí | No | Core.
| `policy_decision.policy_id` (state top) | `phase_policy_planner_node` (`nodes/planner_node.py:268-276`) | `executor_node` (`nodes/executor_node.py:71-78`) | Sí | No | Core.
| `executor_instruction.*` | `phase_policy_planner_node` (`nodes/planner_node.py:80-103,278-296`) | `executor_node` enforcement (`nodes/executor_node.py:28-63,144-152`) | Sí | No | Core.

### Conclusión de matriz RW

- **No hay evidencia para borrar inmediato** de ramas legacy sin instrumentación previa, porque varias aún tienen lectores runtime (especialmente `negotiation`, `universal_state`, `universal_v2`, `negotiation_v2`, `open_claims`).
- Sí hay ramas con lectores **solo telemetry/normalización** (`world_observations*`, `world_derived`, `evidence_items`) donde la ruta segura es: PR1 contadores -> PR2 stop-read por flag -> PR3 delete.

---

## 3) Dead prompts / normalizers / adapters (con método de prueba)

| Candidato | Por qué candidato | Evidencia actual | Cómo demostrar no-uso | Riesgo | Retirada |
|---|---|---|---|---|---|
| Prompt legacy world v3 (`elementos/world_extractor_v3_prompts.py`) | Pipeline actual usa extractor v4; v3 aparece como componente heredado | Import en `extractors/world_extractor_v3.py`; runtime principal llama v4 (`world_state_updater.py:16,352`) | contador de invocaciones legacy y fail test si >0 con flag deprecación | Medio | PR2 shadow + PR3 delete si 0 |
| `world_observations*` normalización en `validation.py` | parece sostener compat histórica | escritura en `validation.py:953-999`; lectura productiva directa limitada | contadores de lectura por key_path + snapshot de trace minimal | Medio | PR2 stop-read, PR3 delete |
| `world_derived` normalización | idem | escritura `validation.py:1005-1010`; reader runtime no identificado | mismo método | Medio | PR2/PR3 |
| `evidence_items` legacy | aparece como write de normalize | `validation.py:945` | contador + rg CI allowlist | Bajo/Medio | PR3 |
| `gating/gate_planner.py` y `gating/shared.py` wrappers deprecados | puente a `legacy/gating_deprecated` | `gate_utils.py:11-13` importa wrappers; uso funcional en tests para `gate_phase_policy` | contador de llamadas runtime por endpoint `/negociar`; si 0 fuera tests -> delete | Medio | PR2 aislado + PR3 delete |
| `legacy/gating_deprecated.py` | explícitamente legacy | usado vía wrappers deprecados (`gating/gate_planner.py`, `gating/shared.py`) | eliminar dependencia interna en gate_utils | Medio | PR2 migrar, PR3 borrar |

---

## 4) Plan de limpieza por PRs (obligatorio)

## PR1 — Observabilidad + stop-export/stop-render (sin cambiar decisiones)

**Cambios:**
1. Añadir contadores de acceso a legacy key-paths (read counters):
   - `world_state`: `universal_domain`, `negotiation`, `universal_state`, `open_claims`, `evidence_items`, `world_observations`, `world_observations_v2`, `world_derived`, `universal_v2`, `negotiation_v2`.
   - `belief_state`: `universal`, `negotiation` subárboles legacy.
2. LiveTrace default = **contract minimal** (buckets/meta/judgement/planner-prog debug).
3. Exposición raw/legacy solo con flag `TRACE_INCLUDE_LEGACY_RAW=1`.

**Criterio de salida PR1:**
- test de shape minimal en `build_trace_event`.
- contadores de lectura presentes en evento/metricas.
- runtime funcional idéntico.

## PR2 — Stop reading / stop writing con flags (compat temporal)

Flags:
- `STATE_DEPRECATE_WORLD_LEGACY=1`
- `STATE_DEPRECATE_BELIEF_LEGACY=1`
- `TRACE_INCLUDE_LEGACY_RAW=0/1`

**Comportamiento:**
- flag ON: no leer legacy salvo fallback explícito (registrado en telemetry).
- flag OFF: compat temporal.

**Criterio de salida PR2:**
- suite ON/OFF verde.
- smoke negociación 3-5 turnos verde.
- contador de read legacy cae a ~0 en ON (excepto allowlist explícita).

## PR3 — Borrado definitivo

**Cambios:**
- eliminar keys legacy en schemas/defaults/validation.
- eliminar prompts/adapters/bridges confirmados sin uso.
- CI: `rg` guardrails anti reintroducción legacy fuera allowlist.

**Criterio de salida PR3:**
- contadores legacy = 0 sostenido.
- CI + E2E negociación verde.
- LiveTrace payload reducido y estable.

---

## 5) CONTRACT MINIMAL (especificación exacta objetivo)

## 5.1 `world_state` minimal objetivo

```json
{
  "schema_version": "v3",
  "world_buckets": {
    "offers": [],
    "concessions": [],
    "constraints": [],
    "interests": [],
    "claims": [],
    "requests": [],
    "context": []
  },
  "world_state_meta": {
    "turn_idx": 0,
    "updated_fields": [],
    "updated_buckets": [],
    "extractor_failed": false,
    "error": "",
    "unknown_claims": []
  },
  "policy_plan_judgement": {
    "schema_version": "v1",
    "plan_status": "continue_same_step"
  }
}
```

## 5.2 `belief_state` minimal objetivo

Opción A (mínimo universal temporal):
```json
{
  "schema_version": "v3",
  "belief_buckets": {
    "hypotheses": [],
    "strategy_notes": [],
    "risk_flags": [],
    "watch_items": []
  },
  "planner_signals": {
    "interaction_health": "stable",
    "conflict_risk": 0.0,
    "recommended_move": "hold"
  }
}
```

Opción B (sin universal, todo bucketizado):
- mover `interaction_health/conflict_risk/recommended_move` a `belief_buckets.strategy_notes/risk_flags` con contrato explícito.

## 5.3 Implicaciones en diff y LiveTrace

- `diff_world_state` debe comparar **solo** `world_buckets + world_state_meta (+ judgement)`.
- LiveTrace “base/new” por defecto: solo estados minimales.
- raw completo bajo `TRACE_INCLUDE_LEGACY_RAW=1`.

---

## 6) Lista de borrado propuesta (priorizada)

## 6.1 Borrar ya (alta confianza)

1. Duplicación interna en `backend/negotiation/telemetry/live_trace.py` (bloque repetido cálculo belief diff, líneas ~80-104).
   - Evidencia: duplicación literal en función `build_trace_event`.
   - Test seguridad: snapshot evento antes/después (igual semántica).

## 6.2 Deprecar primero (media)

1. `world_state.world_observations`, `world_state.world_observations_v2`, `world_state.world_derived`, `world_state.evidence_items`.
   - Evidencia: writers en `validation.py`; readers críticos no confirmados.
   - Test seguridad: contadores read=0 en producción/canary + ON/OFF flags.

2. `world_state.universal_domain`, `world_state.negotiation`, `world_state.universal_state`, `world_state.open_claims`.
   - Evidencia: readers activos hoy (`mode_inference.py`, `world_node.py`, `belief_state_updater.py`).
   - Test seguridad: migrar readers a buckets/meta y validar paridad de decisiones.

3. `belief_state.negotiation` subárbol legacy.
   - Evidencia: writer activo; readers críticos directos limitados.
   - Test seguridad: contador de lectura + parity tests planner/progress/executor.

4. `gating/gate_planner.py`, `gating/shared.py`, `legacy/gating_deprecated.py`.
   - Evidencia: wrappers deprecados aún encadenados por `gate_utils.py`.
   - Test seguridad: ejecución `/negociar` + tests de gate sin wrappers.

## 6.3 No tocar aún (alta dependencia)

1. `update_world_state(...)` y extractor open world.
   - Restricción dura del encargo.

2. `world_buckets`, `belief_buckets`, `policy_plan_judgement`, `progress_state.active_plan*`, `executor_instruction`.
   - Evidencia: core del pipeline y decisión final.

---

## 7) Checklist final DoD (comandos exactos)

## 7.1 Tests
```bash
pytest -q backend/tests/test_api_negotiation_smoke.py
pytest -q backend/tests/test_live_trace_telemetry.py
pytest -q backend/tests/test_negotiation_pipeline_smoke_turns.py
pytest -q backend/tests
```

## 7.2 Verificación de wiring y readers/writers
```bash
rg -n "@app.post\(\"/negociar\"|run_negotiation_agent\(|workflow.add_node|workflow.add_edge" backend/app.py backend/negotiation/negotiation_graph.py
rg -n "def world_updater_node|def belief_updater_node|def policy_progress_node|def phase_policy_planner_node|def progress_updater_node|def executor_node" backend/negotiation/nodes/*.py
rg -n "universal_domain|\bnegotiation\b|universal_v2|negotiation_v2|universal_state|open_claims|evidence_items|world_observations|world_observations_v2|world_derived" backend/negotiation
```

## 7.3 Guardrails CI (a introducir en PR3)
```bash
# fallar si reaparecen keys legacy fuera de allowlist
rg -n "world_observations|world_derived|evidence_items|universal_domain|open_claims" backend/negotiation | rg -v "allowlist_file_or_comment"
```

## 7.4 Métrica payload LiveTrace
```bash
# ejemplo: muestrear JSON SSE y medir tamaño
# (script/test util en CI para avg y p95)
```
Objetivo:
- reducción tamaño promedio y p95 vs baseline pre-PR1.
- contadores read legacy -> 0 antes de PR3.

---

## Conclusión ejecutiva

- El pipeline de negociación activo está claro y único dentro de `/negociar`: grafo de 6 nodos.
- No se justifica borrado ciego de legacy: aún hay readers runtime en ramas legacy concretas.
- Ruta segura obligatoria: **PR1 observabilidad + stop-render**, **PR2 stop-read/write con flags ON/OFF**, **PR3 borrado definitivo con guardrails CI**.
