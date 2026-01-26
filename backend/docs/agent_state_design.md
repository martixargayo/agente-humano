# Diseño de estado del agente (StateAct-like, 2026)

## Por qué estos cambios

- **Normalización tolerante (non-strict)**: se evita que un campo inválido (p. ej. tono) resetee el estado completo, reduciendo discontinuidades que confundían al planner y a las métricas de progreso.
- **Temporalidad correcta (executed vs chosen)**: se separa lo ejecutado de lo elegido, garantizando que el estado persistente refleje acciones realmente ejecutadas.
- **Fallback explícito y trazable**: cuando hay datos inválidos (e.g. `policy_id`), se registra el issue y se aplica un fallback declarado, evitando “autocorrecciones” silenciosas.
- **Estabilidad**: se usa gating por deltas (world_diff + cambios de tono) y smoothing en updates, reduciendo oscilaciones y loops falsos.
- **Source of truth único**: se elimina ambigüedad de campos duplicados, mejorando trazabilidad de debugging y coherencia en el wiring.

### Riesgos eliminados

- **Early return en normalización** → evitaba aplicar el resto del estado → *planner errático/estados discontinuos*.
- **Outcome global por turno** → penalizaba policies no responsables → *bloqueos injustificados*.
- **Campos ambiguos (`last_policy_id`)** → conflicto entre “chosen” y “executed” → *temporalidad inconsistente*.

### Métricas observables que mejoran

- Menos loops falsos por penalización global de outcomes.
- Menor drift por normalización tolerante y smoothing.
- Mayor trazabilidad (issues + `policy_last_outcome`).

### Tradeoffs

- **Costo**: más campos en `ProgressState` y validaciones adicionales.
- **Beneficio**: mayor estabilidad y claridad diagnóstica en producción.

## “Por qué” (rationale por cambio)

### Pytest siempre importable desde raíz

- **Problema observable**: `pytest -q` fallaba con `ModuleNotFoundError` al importar `negotiation` en un checkout limpio.
- **Invariante**: los tests deben correr desde la raíz sin `PYTHONPATH` manual ni dependencias del IDE.
- **Cambio**: se añade `pytest.ini` con `pythonpath = backend` y `backend/tests/conftest.py` queda solo para fixtures/env vars.
- **Por qué esta solución y no otra**: evitar cambios en imports de tests (`backend.negotiation`) reduce acoplamiento y mantiene el import root claro.
- **Riesgos**: depender solo de `pytest.ini` exige que el repo mantenga la carpeta `backend` en su lugar esperado.
- **Mitigación**: el fallo es inmediato si falta `backend` en el repo y no se ocultan errores de packaging.
- **Cómo lo medimos**: `pytest -q` desde raíz y `pytest -q backend/tests/test_state_normalization.py`.
- **Tests**: `pytest -q`.

### Belief gating por flags críticos + tono

- **Problema observable**: si `world_diff` llega vacío, cambios en señales críticas o de tono no disparaban update de belief, dejando el estado stale.
- **Invariante**: cambios en flags críticos y tono deben disparar actualización aunque `world_diff` sea vacío.
- **Cambio**: se valida explícitamente el delta de flags críticos y el cambio de `tone_signal` en `has_belief_evidence_delta`.
- **Por qué esta solución y no otra**: es un chequeo determinista y local, sin depender del extractor de diffs.
- **Riesgos**: se dispara update con más frecuencia (coste de tokens/latencia).
- **Mitigación**: updates siguen sujetos a normalización y a los límites de cambio por turno.
- **Cómo lo medimos**: disminución de `belief_update_skipped` cuando cambian flags o tono.
- **Tests**: `test_has_belief_evidence_delta_triggers_on_critical_flag_change`, `test_has_belief_evidence_delta_triggers_on_tone_change`.

### Compatibilidad con pydantic en modelos de belief

- **Problema observable**: la importación de `belief_state_updater` fallaba en runtime al evaluar `conlist(..., max_items=...)`.
- **Invariante**: los modelos pydantic deben instanciarse sin errores de firma en el entorno de ejecución.
- **Cambio**: se fija `pydantic>=2.7,<3` en `requirements.txt` para cerrar la compatibilidad.
- **Por qué esta solución y no otra**: el pin elimina ambigüedades de firma y evita compat layers innecesarios.
- **Riesgos**: limita la actualización automática a futuras majors de pydantic.
- **Mitigación**: revisar el pin al subir dependencias y ejecutar la suite completa.
- **Cómo lo medimos**: `pytest -q` importa `belief_state_updater` sin excepciones.
- **Tests**: `test_has_belief_evidence_delta_triggers_on_critical_flag_change`, `test_belief_reasons_tiebreak_is_deterministic_with_real_keys`.

### Estabilidad de razones top-K (tie-break determinista total)

- **Problema observable**: empates de score generaban orden no determinista entre razones.
- **Invariante**: a igualdad de score y prioridad, el orden debe ser estable entre runtimes.
- **Cambio**: se añade un tercer criterio determinista (`str(key)`) en el sorting de razones.
- **Por qué esta solución y no otra**: mantiene el orden estable sin reestructurar los modelos ni añadir persistencia externa.
- **Riesgos**: keys lexicográficas podrían sesgar el top-K en empates exactos.
- **Mitigación**: la prioridad explícita sigue dominando; el tercer criterio solo actúa en empates reales.
- **Cómo lo medimos**: menor churn en `belief.reasons` cuando el score es idéntico.
- **Tests**: `test_belief_reasons_tiebreak_is_deterministic_with_real_keys`.

### Normalización robusta de `policy_attempts`

- **Problema observable**: strings numéricos como `"3"` se descartaban, perdiendo intentos reales.
- **Invariante**: `policy_attempts` acepta enteros y strings numéricos; valores inválidos generan issue.
- **Cambio**: coerción a `int` por key con reporte de issues.
- **Por qué esta solución y no otra**: evita romper payloads legacy sin cambiar el schema público.
- **Riesgos**: entradas no numéricas podrían colarse si no se reportan.
- **Mitigación**: issues explícitos por key inválida y exclusión del mapa normalizado.
- **Cómo lo medimos**: reducción de resets de `policy_attempts` por payloads legacy.
- **Tests**: `test_normalize_progress_policy_attempts_accepts_numeric_strings`, `test_normalize_progress_policy_attempts_reports_invalid_values`.

### Planner gating usa outcomes por policy (IDs reales)

- **Problema observable**: el test de gating usaba asserts legacy con IDs dinámicos, haciendo el resultado inconsistente.
- **Invariante**: el gating por outcome debe depender de IDs reales y aislar otros filtros.
- **Cambio**: el test usa `list_policy_ids()` y fuerza condiciones estables (sin otros gates activos).
- **Por qué esta solución y no otra**: evita hardcodear IDs inexistentes y reduce flakiness ante cambios del catálogo.
- **Riesgos**: acoplamiento al catálogo real puede fallar si el catálogo queda vacío.
- **Mitigación**: assert explícito de tamaño mínimo antes de continuar.
- **Cómo lo medimos**: el test falla si la lógica de gating por outcome se rompe.
- **Tests**: `test_allowed_policy_ids_uses_outcome_per_policy`.

### Invariante temporal executed vs chosen (source of truth)

- **Problema observable**: si no persistimos `last_policy_executed` al final del turno, el outcome puede evaluarse en el turno equivocado.
- **Invariante**: lo ejecutado en turno *t-1* es la única fuente de verdad para evaluar outcome en *t*.
- **Cambio**: `run_negotiation_agent` persiste siempre `state.last_policy_executed` desde `executed_policy` (fallback a `policy_decision`) tras normalización.
- **Por qué esta solución y no otra**: evita inferencias indirectas sobre el ejecutado y mantiene consistencia temporal.
- **Riesgos**: si el executor devuelve un policy inválido, podríamos persistir datos inconsistentes.
- **Mitigación**: normalización estricta y issues registrados en `debug_trace`.
- **Cómo lo medimos**: coherencia en `debug_trace` y métricas de `policy_last_outcome` turno a turno.
- **Tests**: `test_update_progress_state_tracks_policy_last_outcome`, `test_temporal_invariant_last_policy_executed_is_persisted`.

## Plantilla “Por qué de las modificaciones” (P0/P1/P2)

### P0 — Executor node: una sola ejecución, DI como fuente única

(1) **Problema observable**: doble ejecución del LLM y reasignación de `full_text` dentro de `executor_node`.  
(2) **Invariante/contrato**: one call per turn, one source of truth (DI).  
(3) **Cambio implementado (con rutas y símbolos exactos)**: `backend/negotiation/negotiation_graph.py::executor_node` usa solo `full_text = deps.execute(messages).strip()` y elimina cualquier `executor_llm.invoke(...)` local.  
(4) **Riesgo si NO se hace**: coste doble, outputs inconsistentes y violación del contrato DI.  
(5) **Tradeoff**: dependencia directa de DI para observabilidad; menor flexibilidad ad-hoc en el nodo.  
(6) **Cómo se mide (comando/test exacto)**: revisión de código + `pytest -q`.  

### P1 — Contrato temporal: executed_policy → last_policy_executed + trace

(1) **Problema observable**: `last_policy_executed` derivaba de `policy_decision` (chosen), no de lo ejecutado real.  
(2) **Invariante/contrato**: separar *chosen* vs *executed* y persistir lo ejecutado como fuente de verdad.  
(3) **Cambio implementado (con rutas y símbolos exactos)**:  
    - `backend/negotiation/negotiation_graph.py::NegotiationTurn` añade `executed_policy`.  
    - `executor_node` fija `state["executed_policy"] = state.get("policy_decision") or default_policy_decision()` antes de `deps.execute(...)`.  
    - `run_negotiation_agent` persiste `state.last_policy_executed` desde `executed_policy_raw` normalizado, y añade `executed_policy_*` al `debug_trace`.  
(4) **Riesgo si NO se hace**: evaluación temporal incorrecta de outcomes y trace ambiguo.  
(5) **Tradeoff**: un campo adicional en el grafo y una normalización extra para auditoría.  
(6) **Cómo se mide (comando/test exacto)**: `pytest -q`.  

### P2 — Evidencia de tests en el PR summary

(1) **Problema observable**: “Testing: Not run” impide validar paper-grade.  
(2) **Invariante/contrato**: todo PR paper-grade debe incluir evidencia de tests con exit 0.  
(3) **Cambio implementado (con rutas y símbolos exactos)**: el summary del PR incluye literalmente `Testing: ✅ pytest -q`.  
(4) **Riesgo si NO se hace**: regresiones sin detectar y revisión bloqueada.  
(5) **Tradeoff**: coste de ejecución local/CI.  
(6) **Cómo se mide (comando/test exacto)**: `pytest -q`.  

## Changelog técnico (deprecaciones y migración)

- **Deprecado**: `last_policy_id` (ambigüo). Se mantiene solo para compatibilidad de sesiones antiguas.
  - **Migración**: `last_policy_id` se mapea a `last_chosen_policy_id` y `last_executed_policy_id` en normalización.
- **Nuevo**: `policy_last_outcome` (mapa `policy_id → outcome`) para gating por policy.
- **Persistencia**: `last_policy_executed` es la única fuente de verdad para el outcome ejecutado por turno.

## Compatibilidad con sesiones antiguas

- `last_policy_executed = {}` o sin `policy_id` se trata como `None`.
- `last_policy_outcome` legado se mapea a `last_executed_policy_outcome`.
- `last_policy_id` legado se mapea a `last_chosen_policy_id` y `last_executed_policy_id`.

## Alineación con prácticas/papers

- **Temporalidad correcta**: separación estricta de *chosen* vs *executed*.
- **Fallback explícito** ante acciones inválidas.
- **Normalizers tolerantes** con modo strict opcional.
- **Delta updates + smoothing** para estabilidad.
- **Source of truth único** para evitar wiring ambiguo.
