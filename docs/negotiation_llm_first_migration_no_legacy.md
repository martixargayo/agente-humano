# Migración LLM-first sin legacy (v3) — negociación

## Principios
- Legacy: dual-schema (`v1/v2`) con campos de dominio rígidos y puentes auxiliares.
- LLM-first: estado mínimo, abierto y estable para planner/executor.
- Regla: `/negociar` opera sobre contrato `v3` y cualquier estado antiguo se migra en carga (`migrate_*_to_v3`) y se *strippea*.

## Paso 0 — Baseline (evidencia literal)

### 0.1 Legacy scan
```bash
rg -n "universal_domain|\bnegotiation\b|universal_v2|negotiation_v2|universal_state|open_claims|evidence_items|world_observations|world_derived" backend/negotiation backend/app.py backend/tests
```
Extracto:
```text
backend/tests/test_world_state_shape.py:6:    assert "universal_domain" in world
backend/tests/test_world_state_shape.py:7:    assert "negotiation" in world
backend/tests/test_e2e_negotiation_pipeline.py:188:    state.world_state = {"negotiation": "oops"}
```

### 0.2 Buckets scan
```bash
rg -n "world_buckets|belief_buckets" backend/negotiation backend/app.py backend/tests
```
Extracto:
```text
backend/negotiation/schemas.py:565:        "world_buckets": {
backend/negotiation/schemas.py:589:        "belief_buckets": {
backend/negotiation/gating/gate_belief.py:25:        return False, "world_buckets_changed"
```

### 0.3 Tests baseline mínimos
```bash
pytest -q backend/tests/test_api_negotiation_smoke.py backend/tests/test_live_trace_telemetry.py
```
Resultado: `8 passed`.

### 0.4 Tamaño LiveTrace (avg/p95)
```bash
PYTHONPATH=backend python backend/scripts/trace_payload_stats.py
```
Salida:
```json
{"events": 20, "avg_bytes": 2923.1, "p95_bytes": 2925}
```

---

## Contrato final v3

### world_state v3
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
  }
}
```

### belief_state v3
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
    "recommended_move": "hold",
    "recovery_mode": false
  }
}
```

---

## Antes vs Después (key-path)

| Antes (legacy) | Después (v3) |
|---|---|
| `world_state.universal_domain.*` | eliminado, reemplazado por `world_buckets.*` + `world_state_meta.*` |
| `world_state.negotiation.*` | eliminado, reemplazado por `world_buckets.*` |
| `world_state.universal_v2.*` | eliminado |
| `world_state.negotiation_v2.*` | eliminado |
| `world_state.open_claims` | migrado a `world_buckets.claims` y eliminado |
| `world_state.evidence_items` | eliminado |
| `world_state.world_observations*` | eliminado |
| `world_state.world_derived` | eliminado |
| `belief_state.universal.*` | migrado a `planner_signals.*` |
| `belief_state.negotiation.*` | migrado a `belief_buckets.*` |
| `intent_*` trace fields | eliminados del runtime trace |

---

## Archivos tocados y por qué
- `backend/negotiation/state_migration_v3.py`: migración idempotente legacy -> v3.
- `backend/state.py`: aplicación automática de migración al cargar sesión.
- `backend/negotiation/schemas.py`: defaults v3 minimal.
- `backend/negotiation/validation.py`: normalización v3-only.
- `backend/negotiation/world_state_updater.py`: world updater/diff sobre buckets+meta.
- `backend/negotiation/belief_state_updater.py`: belief updater v3 (`belief_buckets` + `planner_signals`).
- `backend/negotiation/phase_state_updater.py`: lectura desde buckets/signals.
- `backend/negotiation/mode_inference.py`: inferencia desde buckets.
- `backend/negotiation/telemetry/live_trace.py`: payload minimal sin raw legacy.
- `backend/app.py`: panel LiveTrace adaptado a evento minimal.
- `backend/negotiation/gating/*`: limpieza de wrappers legacy.
- `backend/tests/test_state_migration_v3.py`: prueba de migración+strip.
- `backend/tests/test_no_legacy_keys_in_negotiation_runtime.py`: guardrail anti reintroducción.

---

## Guardrails / verificación

```bash
pytest -q backend/tests/test_state_migration_v3.py backend/tests/test_no_legacy_keys_in_negotiation_runtime.py
pytest -q backend/tests/test_api_negotiation_smoke.py backend/tests/test_live_trace_telemetry.py
rg -n "universal_domain|negotiation_v2|universal_v2|universal_state|open_claims|evidence_items|world_observations|world_derived|intent_step|intent_transition" backend/negotiation
```

DoD:
- runtime `/negociar` en v3;
- migración load-time + strip;
- trace minimal sin raw legacy;
- guardrail activo;
- tests verdes.
