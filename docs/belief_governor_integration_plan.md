# Integración de hipótesis de Belief en planner/policy/executor (diseño incremental)

## 1) INVENTARIO REAL DEL REPO (rutas exactas)

### 1.1 Dónde se define/actualiza/normaliza `belief_state`

- **Contrato base + defaults**:
  - `backend/negotiation/schemas.py`
    - `BeliefState`, `BeliefUniversalState`, `BeliefNegotiationState`.
    - `default_belief_state()`.
- **Actualización por turno (LLM + merge)**:
  - `backend/negotiation/belief_state_updater.py`
    - `extract_belief_patch_llm_v2(...)` (extrae `universal_patch`, `negotiation_patch`).
    - `update_belief_state(...)` (gating + merge + normalización final).
    - `merge_belief_universal(...)` (clamp por paso, merge conservador).
- **Normalización determinista**:
  - `backend/negotiation/validation.py`
    - `normalize_belief_universal(...)` (allowlist fuerte para `universal.reasons`, clamp, límites ToM).
    - `normalize_belief_state(...)` (estructura v2; hoy `negotiation.stance/reasons` quedan blandos).
- **Migración legacy→v2 en estado de sesión**:
  - `backend/state.py`
    - `migrate_belief_state_legacy_to_v2(...)`.

### 1.2 Dónde se construye el prompt del planner

- `backend/negotiation/phase_policy_planner.py`
  - Usa `PHASE_POLICY_SYSTEM_PROMPT` + `PHASE_POLICY_USER_PROMPT`.
  - Renderiza payload con `world_state`, `world_diff`, `belief_state`, etc. en `plan_phase_policy(...)`.
- Plantillas de prompt:
  - `backend/prompts.py` (`PHASE_POLICY_SYSTEM_PROMPT`, `PHASE_POLICY_USER_PROMPT`).

### 1.3 Dónde se calcula `allowed_policy_ids` y se valida `policy_decision`

- **Cálculo de elegibilidad**:
  - `backend/negotiation/policy_planner.py`
    - `allowed_policy_ids_no_phase(...)` (hoy ignora `belief_state`).
    - `allowed_policy_ids(...)` (también ignora `belief_state`).
    - `_required_inputs_met(...)` (solo world inputs).
- **Orquestación planner + validación**:
  - `backend/negotiation/nodes/planner_node.py`
    - Llama `allowed_policy_ids_no_phase(...)`.
    - Llama `deps.plan_phase_policy(...)`.
    - Repara por fase y normaliza con `normalize_policy_decision(...)`.
- **Normalización de decisión**:
  - `backend/negotiation/validation.py`
    - `normalize_policy_decision(...)` valida `policy_id` contra allowlist y corrige campos.

### 1.4 Dónde se construye `constraints_struct`

- `backend/negotiation/elementos/render/constraints_builder.py`
  - `build_constraints_struct(...)`.
  - Hoy solo usa:
    - `style.max_questions`,
    - `belief.universal.dynamics.interaction_health` (reduce preguntas si `tense/stalled`),
    - guards de policy (`avoid_mentioning_own_numbers`),
    - `world.negotiation.price_mentioned` para `require_ask_if_missing`.

### 1.5 Dónde se renderiza el prompt del executor

- `backend/negotiation/executor/render_executor.py`
  - `render_executor_output(...)` construye prompt final.
  - `summarize_belief_state_for_executor(...)` crea resumen acotado de belief.
- Prompt del executor:
  - `backend/negotiation/elementos/render/executor_prompts.py`.

### 1.6 Dónde se guarda/propaga `belief_state` en el grafo

- Nodos y secuencia:
  - `backend/negotiation/negotiation_graph.py` (pipeline world→belief→planner→executor).
  - `backend/negotiation/nodes/belief_node.py` (invoca `update_belief_state`).
- Persistencia en sesión:
  - `backend/negotiation/negotiation_graph.py` (`run_negotiation_agent` actualiza `state.belief_state`).
  - `backend/state.py` (dataclass `SessionState` y carga/migración).

---

## 2) DIAGNÓSTICO

## 2.1 Qué sí usa hoy el sistema de `belief_state`

- **Planner (indirecto)**:
  - `plan_phase_policy(...)` recibe `belief_state` completo en prompt (input LLM).
  - Pero la **elegibilidad determinista** de policies no lo usa.
- **Constraints builder (determinista)**:
  - Usa `belief.universal.dynamics.interaction_health` para modular `max_questions`.
- **Executor (LLM)**:
  - Recibe `belief_state_summary` con claves universales y de negociación, incluyendo hipótesis.

## 2.2 Qué NO está gobernado (problema crítico)

- `tom`/hipótesis libres (universal y negotiation) **no tienen traducción determinista a señales gobernantes**.
- `allowed_policy_ids` **no aplica condiciones de belief** (`required_beliefs` no existe).
- `negotiation.stance` y `negotiation.reasons` permanecen con validación blanda.
- El executor ve hipótesis en resumen, pero **sin contrato epistemológico explícito** (riesgo de afirmarlas como hechos).

## 2.3 Impacto actual

- El sistema puede “pensar” hipótesis pero no convertirlas consistentemente en:
  1. selección de phase/policy,
  2. filtro determinista de elegibilidad,
  3. estilo conversacional seguro (hedging/verificación).
- Resultado: baja utilidad conductual de la capa Belief y riesgo de deriva si se consume `tom` sin gobernanza.

---

## 3) DISEÑO PROPUESTO (HÍBRIDO VÍA 1 + VÍA 2)

> Recomendación: **híbrido**.
> - Vía 1 para traducir hipótesis libres a señales allowlisted.
> - Vía 2 para usar esas señales en elegibilidad de policy y ejecución, pero de forma determinista.

### 3.1 Principio rector

Patrón obligatorio conservado:

**LLM propone → normalizador determinista filtra → governor determinista sintetiza señales gobernantes → planner/eligibility/executor consumen solo señales gobernantes.**

### 3.2 Separación contractual “libre vs gobernante”

- **Libre (no gobernante directo)**:
  - `belief.universal.tom.*`
  - `belief.negotiation.hypotheses*`
  - `belief.negotiation.tom`
- **Gobernante (allowlist duro)**:
  - `belief.universal.reasons` (ya existe allowlist fuerte)
  - `belief.negotiation.stance` (nuevo allowlist duro)
  - `belief.negotiation.reasons` (nuevo allowlist duro)
  - `belief.universal.behavior_guidance` (**nuevo**, salida determinista del governor)

### 3.3 Nuevo contrato: `behavior_guidance`

Agregar en `belief.universal`:

```json
{
  "behavior_guidance": {
    "assertiveness": 0.0,
    "verification_need": 0.0,
    "trust_estimate": 0.0,
    "conflict_risk": 0.0,
    "pace_preference": 0.0,
    "recommended_move": "probe|reframe|deescalate|close|hold|tradeoff",
    "epistemic_style": "hedged|neutral|direct"
  }
}
```

Reglas:
- Numeric clamps `[0,1]`.
- `recommended_move` y `epistemic_style` con enum cerrado.
- Solo se calcula en función de:
  - `universal.metrics/dynamics/reasons`,
  - `negotiation.stance/reasons` normalizados,
  - señales observables de world.
- **Nunca** desde hipótesis libres de forma directa (solo como input ponderado + límites).

### 3.4 Belief Governor determinista

Nueva función (pura) propuesta:

`derive_behavior_guidance(belief_state, world_state) -> (guidance, issues)`

- Entradas:
  - belief normalizado v2,
  - world normalizado.
- Salida:
  - `behavior_guidance` allowlisted + metadatos de trazabilidad (`drivers`).
- Heurísticas deterministas (ejemplo):
  - más `evasion_signal` + `docs_signal` bajo + `other_buyer_signal` incierto => sube `verification_need`.
  - `interaction_health=tense|stalled` => sube `conflict_risk`, baja `pace_preference`, fuerza `epistemic_style=hedged`.
  - `commitment=hard` + alta cooperación + evidencia sólida => permite `epistemic_style=neutral|direct`.

### 3.5 Vía 2 complementaria: `required_beliefs` en policy eligibility

Extender contrato de policy para permitir:

```json
"required_beliefs": [
  {"key": "universal.behavior_guidance.verification_need", "op": "gte", "value": 0.6},
  {"key": "universal.dynamics.interaction_health", "op": "eq", "value": "tense"}
]
```

- Nueva función determinista:
  - `_required_beliefs_met(policy_id, belief_state) -> bool`.
- Integrar en:
  - `allowed_policy_ids_no_phase(...)`
  - `allowed_policy_ids(...)`

### 3.6 Seguridad epistemológica (obligatoria)

- Prompt executor con contrato explícito:
  - hipótesis inferenciales se verbalizan con hedging:
    - “parece que…”,
    - “podría ser…”,
    - “para confirmar…”.
- Prohibición explícita:
  - no afirmar hipótesis como hecho si su fuente es inferencial.
- Regla operacional:
  - si `verification_need >= umbral`, priorizar preguntas de verificación sobre afirmaciones fuertes.

### 3.7 Compatibilidad incremental

- Feature flags:
  - `BELIEF_GOVERNOR_ENABLED` (default off en rollout inicial).
  - `POLICY_REQUIRED_BELIEFS_ENABLED`.
  - `EXECUTOR_EPISTEMIC_CONTRACT_ENABLED`.
- Dual-read:
  - si falta `behavior_guidance`, fallback a defaults seguros.
- Sin romper endpoints:
  - `/chat` y `/negociar` conservan flujo; el cambio es interno al estado y a filtros.

---

## 4) CAMBIOS CONCRETOS POR ARCHIVO

## 4.1 Contratos + normalización

- `backend/negotiation/schemas.py`
  - Añadir TypedDict `BehaviorGuidance`.
  - Extender `BeliefUniversalState` con `behavior_guidance`.
  - Extender `PolicySpec`/estructura de policy con `required_beliefs` (si aplica en definiciones).
  - Defaults de guidance.

- `backend/negotiation/validation.py`
  - Añadir normalizador de `behavior_guidance` (clamp/enums/drop unknown).
  - Endurecer `negotiation.stance` y `negotiation.reasons` con allowlist explícita.
  - En `normalize_belief_state`, normalizar negotiation con esquema cerrado y límites.

- `backend/negotiation/elementos/belief/belief_contracts.py`
  - Definir allowlists de `NEGOTIATION_STANCE_KEYS` y `NEGOTIATION_REASON_KEYS`.
  - Definir enums de `recommended_move` y `epistemic_style`.

## 4.2 Governor y actualización de belief

- **Nuevo** `backend/negotiation/belief_governor.py`
  - `derive_behavior_guidance(...)`.
  - `summarize_belief_cues_for_planner(...)` (solo señales gobernantes).
  - `summarize_epistemic_contract_for_executor(...)`.

- `backend/negotiation/belief_state_updater.py`
  - Después de `normalize_belief_state(...)`, calcular governor (flaggeado).
  - Persistir `belief.universal.behavior_guidance`.
  - Añadir meta de trazabilidad (`guidance_drivers`, `governor_version`).

## 4.3 Policy eligibility + planner

- `backend/negotiation/policy_planner.py`
  - Añadir `_required_beliefs_met(...)` con ops `eq|neq|gte|lte|in`.
  - Integrar chequeo en `allowed_policy_ids_no_phase(...)` y `allowed_policy_ids(...)`.

- `backend/negotiation/phase_policy_planner.py`
  - Inyectar al prompt `belief_cues` (resumen allowlisted del governor, no hipótesis crudas).

- `backend/prompts.py`
  - Ampliar `PHASE_POLICY_USER_PROMPT` con bloque `[Belief cues governantes]`.
  - Reforzar instrucción de no usar hipótesis no gobernadas.

## 4.4 constraints_struct + executor

- `backend/negotiation/elementos/render/constraints_builder.py`
  - Consumir `behavior_guidance` para:
    - `max_questions` (↑ cuando verification_need alta, con cap),
    - `require_ask_if_missing` (añadir `evidence/docs` cuando aplique),
    - `disallow_numbers` en escenarios de alta incertidumbre táctica (si política lo exige).

- `backend/negotiation/executor/render_executor.py`
  - `summarize_belief_state_for_executor(...)`: excluir hipótesis libres del bloque gobernante.
  - Incluir `epistemic_contract` derivado del governor.

- `backend/negotiation/elementos/render/executor_prompts.py`
  - Añadir reglas explícitas de lenguaje hedged.
  - Prohibir afirmaciones categóricas sobre inferencias no verificadas.

## 4.5 Integración en grafo y observabilidad

- `backend/negotiation/nodes/belief_node.py`
  - Guardar metadatos del governor en `belief_update_meta`.

- `backend/negotiation/negotiation_graph.py`
  - Trazar en debug:
    - `behavior_guidance_prev/new`,
    - `governor_used`,
    - `required_beliefs_filtered_count`.

- `backend/negotiation/telemetry/trace.py`
  - Añadir helpers para diffs de guidance y contadores de drops/filters.

---

## 5) TESTING (unit + e2e + anti-deriva)

## 5.1 Unit tests

- **Nuevo** `backend/tests/test_belief_governor.py`
  - clamp/enums/defaults de `behavior_guidance`.
  - hipótesis libres no alteran guidance si no hay evidencia gobernante.

- Extender `backend/tests/test_belief_normalization_v2.py`
  - allowlist dura en `negotiation.stance/reasons`.
  - drop unknown keys en negotiation.

- **Nuevo** `backend/tests/test_policy_required_beliefs.py`
  - `_required_beliefs_met` por operador.
  - `allowed_policy_ids_*` filtra correctamente por belief.

- Extender `backend/tests/test_constraints_struct_builder.py`
  - `verification_need` modula `max_questions` y `require_ask_if_missing`.

- Extender `backend/tests/test_render_executor_belief_summary.py`
  - resumen del executor contiene cues gobernantes, no hipótesis crudas.

## 5.2 E2E

- Extender `backend/tests/test_e2e_negotiation_pipeline.py` con escenarios:
  1. **bluff inferido** → sube `verification_need`, planner favorece `probe/test_credibility`, executor pregunta para confirmar (sin acusar como hecho).
  2. **alta tensión + baja claridad** → `epistemic_style=hedged`, menor asertividad.
  3. **evidencia documental fuerte** → baja necesidad de hedging y permite cierre gradual.

## 5.3 Tests anti-deriva

- caso: inyectar hipótesis libres extremas con reasons vacías ⇒
  - guidance permanece en defaults seguros,
  - policy elegible no cambia por ese ruido,
  - executor evita afirmaciones categóricas.

---

## 6) PLAN POR PRs (incremental, producción)

### PR-1 (contratos + normalización)
- `BehaviorGuidance` + allowlists negotiation fuertes + normalizadores.
- Sin activar consumo funcional (solo estado y tests).

### PR-2 (governor)
- Nuevo `belief_governor.py`, cómputo determinista y telemetría.
- Flag `BELIEF_GOVERNOR_ENABLED`.

### PR-3 (policy eligibility)
- `required_beliefs` + `_required_beliefs_met` + filtros en allowed policies.
- Flag `POLICY_REQUIRED_BELIEFS_ENABLED`.

### PR-4 (planner/executor wiring)
- `belief_cues` al planner y `epistemic_contract` al executor.
- Prompt rules de hedging.
- Flag `EXECUTOR_EPISTEMIC_CONTRACT_ENABLED`.

### PR-5 (e2e + hardening)
- Escenarios bluff/confirmación, tensión, anti-deriva.
- Rollout gradual y métricas de estabilidad.

---

## 7) CHECKLIST DE ACEPTACIÓN

- [ ] `tom`/intuiciones influyen en planner/executor **solo** vía señales allowlisted (`behavior_guidance` + cues gobernantes).
- [ ] `allowed_policy_ids` aplica condiciones de belief deterministas (`required_beliefs`).
- [ ] executor usa lenguaje hedged cuando la señal es inferencial.
- [ ] no hay invented keys tras normalización.
- [ ] `/chat` y `/negociar` continúan funcionales.
- [ ] hipótesis libres no alteran policy si el governor no lo permite.
- [ ] trazas/telemetría muestran drivers del governor y filtros aplicados.
