# Plan de migración a filosofía LLM-first (world/belief)

## Objetivo

Eliminar heurística lingüística hardcodeada del pipeline de negociación y mover la interpretación semántica al extractor LLM, dejando al código como capa de infraestructura:

- contrato de salida (schema),
- normalización y merge,
- fingerprint/diff,
- gating mecánico,
- observabilidad y control de coste.

---

## 1) Cambios concretos en `world_extractor`

### 1.1 `backend/negotiation/extractors/world_extractor_v4.py`

**Situación actual**

`world_extractor_v4` es un wrapper fino sobre `v3` y no añade contrato semántico fuerte para `negotiation_v2`.

**Cambio propuesto**

1. Mantener `world_extractor_v4` como entrada única, pero exigir output con contrato explícito de material negociable.
2. Extender el resultado del extractor para incluir un bloque `negotiation_v2_patch` (además del patch legacy), con esta intención mínima:
   - `subject`
   - `offers[]`
   - `constraints[]`
   - `concessions[]`
3. Reforzar el prompt con invariantes no lingüísticos:
   - Si hay intercambio/condición/compromiso => `offers` no vacío.
   - Si faltan cifras => `unknown_amounts=true`.
   - Cada item debe incluir `raw_text` y `confidence`.

**Nota**: esto no impone regex ni patrones de lenguaje en código; sólo pide forma de salida.

### 1.2 Prompt contract (`backend/negotiation/elementos/world_extractor_v3_prompts.py`)

Añadir al contrato:

- regla de grounding:
  - `raw_text` obligatorio por item;
  - `evidence_spans` opcional (si el modelo puede devolver offsets de forma confiable);
- política de no invención:
  - no inventar cifras/fechas no expresadas;
  - usar `unknown_amounts=true` cuando corresponda.

### 1.3 Fallback del extractor en `backend/negotiation/world_state_updater.py`

**Eliminar fallback semántico por heurística**:

- retirar gradualmente `_apply_world_backstop` y `_merge_negotiation_v2_terms` para inferir contenido por regex.
- sustituir por fallback genérico:
  - `extractor_failed=true`
  - `last_update_source="llm"`
  - `error=<detalle>`
  - `no_change` sobre campos semánticos

Esto protege consistencia sin volver a meter interpretación en código.

---

## 2) Cambios concretos en `normalize_world_state`

### 2.1 `backend/negotiation/validation.py`

Añadir normalización/invariantes de `negotiation_v2` centradas en utilidad y auditabilidad:

1. `offers`, `constraints`, `concessions` siempre listas (vacías por defecto).
2. Para cada item de esas listas:
   - `raw_text` string (puede ser vacío sólo si `confidence` muy bajo y marcado como inferencia).
   - `confidence` float [0, 1].
3. `unknown_amounts` permitido/normalizado en `offers[].value`.
4. Límite de tamaño por lista (p. ej. top-N por confianza) para coste/memoria.

### 2.2 Invariante de “material negociable no vacío”

Sin usar heurística textual:

- si extractor reporta en meta que detectó intercambio (`meta.negotiation_signal=true`),
  entonces normalización valida que `offers` no sea vacío.
- si viene vacío, registrar issue de validación (`negotiation_signal_without_offers`) y mantener trazabilidad.

Clave: la señal la da la LLM (meta del extractor), no regex en código.

### 2.3 Observabilidad

Asegurar que `world_state_meta.updated_fields` refleje rutas v2 cambiadas:

- `negotiation_v2.subject`
- `negotiation_v2.offers`
- `negotiation_v2.constraints`
- `negotiation_v2.concessions`

para que Live Trace muestre cambios reales del material negociable.

---

## 3) Cambios concretos en `gate_belief`

### 3.1 `backend/negotiation/gating/gate_belief.py`

**Problema actual**

El hold depende de `world_diff`/flags y puede congelar belief aunque cambie material útil en `negotiation_v2`.

**Cambio propuesto**

1. Añadir fingerprint estructural de `negotiation_v2` (mecánico, no lingüístico), basado en:
   - `subject.item/context`
   - contenido canónico de `offers/constraints/concessions`.
2. Nuevo input en gate state:
   - `prev_negotiation_v2_fingerprint`.
3. Regla:
   - si cambió fingerprint estructural => `belief_skipped=false` (`delta_or_signal`).
   - si no cambió y no hay otras señales => mantener `no_delta_interval_hold`.

### 3.2 `backend/negotiation/nodes/belief_node.py`

Persistir/actualizar fingerprint v2 por turno en `gate_state` para la comparación del siguiente turno.

---

## 4) Cambios de robustez de parse (sin heurística semántica)

### 4.1 World

En `world_state_updater.py`, ante JSON inválido:

1. intento parse normal,
2. intento repair JSON genérico,
3. fallback `no_change` + meta de error.

Sin crear contenido de negociación por código.

### 4.2 Belief

Mantener y endurecer la estrategia ya existente en `belief_state_updater.py`:

- parse normal + reparación básica,
- si falla, usar fallback conservador explícito con meta (`belief_fallback_used`, `belief_fallback_reason`).

---

## 5) Plan de implementación por fases

### Fase A (compatibilidad)

- extender contrato de extractor y normalización (`raw_text`, `confidence`, `unknown_amounts`),
- añadir fingerprint estructural v2 (sin cambiar aún todo el gating).

### Fase B (switch de gating)

- `gate_belief` prioriza fingerprint `negotiation_v2` para decidir refresh,
- mantener interval/cooldown actuales para coste.

### Fase C (limpieza)

- retirar heurísticas semánticas de world updater (regex/backstops de contenido),
- conservar sólo fallback técnico/operativo.

---

## 6) Criterios de aceptación

1. El sistema ya no depende de patrones regex para detectar ofertas/intercambios.
2. En turnos con intercambio real, `negotiation_v2` cambia de forma auditable (`raw_text`, `confidence`).
3. `belief` refresca por cambio de fingerprint estructural aunque `world_diff` legacy sea pequeño.
4. Fallos de parse no generan invención de estado; quedan trazados con meta de error.

---

## 7) Riesgos y mitigaciones

- **Riesgo**: mayor variabilidad de extracción LLM.
  - **Mitigación**: schema estricto + normalización fuerte + top-N por confianza.
- **Riesgo**: pérdida temporal de recall al retirar heurísticas.
  - **Mitigación**: migración por fases y métricas de cobertura de offers.
- **Riesgo**: coste de tokens si se fuerza extractor en exceso.
  - **Mitigación**: mantener gating por intervalo/fingerprint, no por regex.

