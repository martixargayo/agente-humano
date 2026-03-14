# 04 — Orquestación y jobs

## 0) Restricción de integración segura

Este subsistema es **post-cierre** y aditivo. No altera el flujo en caliente de turnos (`/api/interfaz_usuario/negociacion/turn`) ni modifica la lógica de `run_negotiation_cognitive_turn`.

## 1) Estados del job

1. `created`
2. `queued`
3. `building_inputs`
4. `running_core`
5. `running_trajectory`
6. `assembling_report`
7. `completed`
8. `failed`

Terminales: `completed`, `failed`.

## 2) Persistencia v1 cerrada

### Decisión v1

- **Repositorio abstracto estable** (`FeedbackRepository`).
- **Implementación concreta inicial**: in-memory process-safe con lock (`InMemoryFeedbackRepository`).

### Motivo

- coherente con `sessions.state` actual (RAM),
- entrega rápida y bajo riesgo sobre flujo existente,
- migrable a durable storage sin romper API.

### Migración v1.1+

Implementar `SqlFeedbackRepository` (SQLite/Postgres) con misma interfaz y mismas claves lógicas (`evaluation_id`, `session_ref`).

## 3) Artefactos congelados (freeze)

Al crear `evaluation_id`, congelar y hashear:

1. `session_history_snapshot`
2. `canonical_snapshot` (solo lectura)
3. `recent_dialogue_snapshot`
4. `trace_digest_source_snapshot` (si aplica)
5. `feedback_input_bundle_v1`
6. `core_runner_request` / `trajectory_runner_request`
7. `core_runner_output` / `trajectory_runner_output`
8. `ui_feedback_report_v1` (si éxito)
9. `error_report` (si fallo)

Hashes mínimos: `sha256` para bundle, prompts, outputs y reporte final.

## 4) Flujo backend detallado

## Paso 0 — Trigger

`POST /api/interfaz_usuario/feedback/evaluations`

Payload: `user_id`, `session_id`, `domain="negociacion"`.

## Paso 1 — Create + queue

- generar `evaluation_id`,
- persistir registro job (`created`),
- pasar a `queued`.

## Paso 2 — Building inputs

- cargar sesión por `get_session_state`,
- freeze snapshots,
- construir `feedback_input_bundle_v1` con prioridad diálogo,
- construir subinputs por runner (ver `11_input_shaping_and_runner_inputs.md`),
- validar.

## Paso 3 — Runners

- `running_core` y `running_trajectory` en paralelo,
- invocar Responses API con `gpt-5.4` para ambos,
- guardar request/response + metadata (model, prompt_version, schema_version, latency).

## Paso 4 — Assembly + reconciliation

- validar outputs,
- aplicar reglas de reconciliación (ver `03_contracts.md`),
- ensamblar `ui_feedback_report_v1`.

## Paso 5 — Complete/failed

- persistir resultado final o error report,
- actualizar estado terminal,
- exponer por polling.

## 5) Endpoints v1

1. `POST /api/interfaz_usuario/feedback/evaluations`
2. `GET /api/interfaz_usuario/feedback/evaluations/{evaluation_id}`
3. `GET /api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report`

## 6) Qué guardar si falla

Siempre persistir:

- `evaluation_id`, `job_state`, `failed_stage`,
- hashes de artefactos disponibles,
- validaciones fallidas,
- outputs parciales si existen,
- timestamp de error.

Objetivo: reproducibilidad y debugging sin romper UX del chat.

## 7) Garantía “no romper interfaz_usuario”

- no tocar endpoint de turnos,
- no inyectar esperas síncronas en envío de mensajes,
- no cambiar contrato actual de `NegotiationTurnResponse`,
- usar nuevos endpoints aislados bajo `/api/interfaz_usuario/feedback/*`.
