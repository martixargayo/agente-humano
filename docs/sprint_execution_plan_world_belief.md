# Plan de ejecución por sprints (solo diseño, sin cambios de código)

Este documento convierte el inventario previo en una secuencia de ejecución **S1/S2/S3**, con orden sugerido de PRs y criterios de salida. El foco es migración controlada a **World v2 + Belief v2** preservando compatibilidad del pipeline actual.

## Objetivos

- Introducir contratos de datos versionados (`world_state`, `belief_state`) con validación determinista.
- Mantener estabilidad funcional en `/chat` y `/negociar` durante la migración.
- Separar señales libres (diagnóstico) de señales gobernantes (policy/planner).
- Habilitar apagado progresivo de legado `v1` con telemetría y regresión controlada.

## Supuestos de diseño

- No se modifica estrategia base de fases del planner ni reglas actuales del executor.
- `conversation_mode` actual se conserva; los cambios son internos a estado/contexto.
- Las decisiones gobernantes no leen hipótesis libres (`tom.hypotheses`).
- La migración se hace con estrategia **dual write/read + fallback**.

---

## Sprint S1 — Contratos, normalización y migración base

### Resultado esperado

Infraestructura de datos versionada operativa sin alterar comportamiento de negocio:

- Contratos `v2` definidos.
- Normalizadores deterministas funcionando.
- Adapters `v1↔v2` listos.
- Tests de forma, filtros y migración en verde.

### PRs sugeridos

#### PR S1.1 — Contratos y defaults

**Alcance (diseño):**
- Nuevo módulo de contratos centrales (`schema_version`, enums, límites, allowlists).
- Defaults `world/belief` para `v1` y `v2`.
- Extensión de `SessionState` para persistir `world_state`/`belief_state` y versión.

**DoD:**
- Estado serializable con `schema_version` explícito por turno.
- Allowlists documentadas y trazables.

#### PR S1.2 — Normalizadores deterministas v2

**Alcance (diseño):**
- `normalize_world_state_v2` y `normalize_belief_state_v2`.
- Reglas: cast/trim/clamp/defaults/truncation/drop unknown keys.
- Política `reasons` sin `evidence` => drop.
- `meta` libre pero acotado (depth/keys/chars).

**DoD:**
- Funciones puras y deterministas.
- Cobertura de casos borde (enums inválidos, arrays gigantes, tipos erróneos).

#### PR S1.3 — Adapters de compatibilidad

**Alcance (diseño):**
- `world_v1_to_v2`, `belief_v1_to_v2`, `world_v2_to_v1_fallback`.
- Mapeos mínimos explícitos para aliases de legado.
- Estrategia de convivencia documentada: A dual write, B dual read.

**DoD:**
- Lectores legacy siguen operativos con fallback.
- Tests de roundtrip básico y no regresión de forma.

### Riesgos S1

- **Filtro demasiado estricto**: pérdida de señal útil.
  - Mitigación: límites calibrados + telemetría de drops.
- **Ambigüedad de alias v1**: migraciones inconsistentes.
  - Mitigación: tabla de mapeo canónica en adapters.

---

## Sprint S2 — Extractores, gating y conexión al pipeline

### Resultado esperado

Pipeline integrado con extracción estructurada y gating robusto, manteniendo estabilidad funcional.

### PRs sugeridos

#### PR S2.1 — World extractor v4 y Belief extractor v3

**Alcance (diseño):**
- Nuevos prompts JSON-only para parches `world/belief`.
- Plantillas con contexto mínimo + estado previo.
- Enforcements de strict output (sin texto extra).

**DoD:**
- Respuestas LLM parseables de forma consistente.
- Errores de formato no propagan estado inválido.

#### PR S2.2 — Integración de update pipeline

**Alcance (diseño):**
- Paso por turno: extracción -> normalización -> merge -> persistencia.
- `has_belief_evidence_delta_v2` para gating de cambios relevantes.
- Mantener separación por endpoint/mode actual.

**DoD:**
- Flujo actual no se rompe (chat/negociar).
- Cambios irrelevantes no disparan transiciones no deseadas.

#### PR S2.3 — Context bridge planner/executor

**Alcance (diseño):**
- Inyectar resumen corto de `stance/reasons` al contexto operativo.
- Crear `constraints_struct builder` para consumo futuro, sin alterar reglas actuales.

**DoD:**
- Planner conserva validación de índice/clamp y estabilidad de fases.
- `tom.hypotheses` excluido de señales gobernantes.

### Riesgos S2

- **Sobre-influencia del belief en la estrategia**.
  - Mitigación: puente informativo acotado y allowlist dura.
- **Drift entre extractor y normalizador**.
  - Mitigación: fixtures compartidas + tests de contrato.

---

## Sprint S3 — Telemetría, hardening y apagado controlado de v1

### Resultado esperado

Sistema observable y seguro para transición final, con criterio objetivo para apagar legado.

### PRs sugeridos

#### PR S3.1 — Telemetría de normalización y versionado

**Alcance (diseño):**
- Eventos/contadores por turno:
  - `world_schema_version_used`, `belief_schema_version_used`
  - `normalization_issues_count`
  - `dropped_keys_count`, `dropped_reasons_count`
  - `adapter_used`
- Exponer hipótesis solo en canales internos de debug.

**DoD:**
- Métricas disponibles para comparar salud v1 vs v2.
- Sin dependencia de hipótesis en policy/planner.

#### PR S3.2 — Test suite de hardening y regresión final

**Alcance (diseño):**
- Suites nuevas/extendidas:
  - normalización world/belief v2,
  - migración v1↔v2,
  - truncation/max_items,
  - regresión e2e de flujo legacy.
- Fixtures de escenarios difíciles (bluff, urgencia contradictoria, evidencia documental).

**DoD:**
- Gates de CI con cobertura mínima acordada.
- Regresión legacy estable.

#### PR S3.3 — Plan de cutover y retiro de v1

**Alcance (diseño):**
- Checklist operacional para desactivar dual write.
- Ventana de observación + rollback plan.
- Criterios de salida cuantitativos (ej. tasa de drops aceptable, parse failures < umbral).

**DoD:**
- Go/No-Go explícito para retirar v1.
- Runbook de incidente post-cutover.

### Riesgos S3

- **Apagado prematuro de v1**.
  - Mitigación: umbrales + periodo de sombra + rollback inmediato.
- **Ruido de telemetría**.
  - Mitigación: taxonomía de errores estable y dashboards mínimos.

---

## Orden recomendado de PRs (global)

1. S1.1 Contratos/defaults
2. S1.2 Normalizadores v2
3. S1.3 Adapters v1↔v2
4. S2.1 Extractores world/belief
5. S2.2 Integración de pipeline + gating
6. S2.3 Context bridge planner/executor + constraints builder
7. S3.1 Telemetría de esquema/normalización
8. S3.2 Hardening tests + fixtures
9. S3.3 Cutover plan y retiro v1

## Criterios de aceptación transversales

- `world_state.schema_version` y `belief_state.schema_version` presentes siempre.
- Extractores con salida JSON-only parseable.
- Normalizadores aplican clamp/cast/defaults/allowlist/truncation.
- `reasons` sin `evidence` se eliminan.
- `tom.hypotheses` no influye policy/planner.
- Modos `/chat` y `/negociar` mantienen comportamiento funcional.
- Adapter/fallback pasa regresión en CI.
- Telemetría reporta drops/correcciones/versiones.
- Existe ruta segura para apagar `v1` tras ventana de estabilidad.


> Nota: para el rediseño específico de integración de hipótesis/intuiciones en planner-policy-executor, ver `docs/belief_governor_integration_plan.md`.
