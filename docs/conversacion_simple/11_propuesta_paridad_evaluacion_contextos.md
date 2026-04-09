# Plan de implementación exacto (sin ejecutar cambios todavía)
## Paridad real de evaluación multicontexto entre `negociacion` y `conversacion_simple`

> Documento de ejecución técnica: **qué código se tocará, cómo se tocará y en qué orden**, sin modificar runtime en esta iteración.

---

## 1) Objetivo técnico (criterio de diseño)

Implementar evaluación multicontexto para `conversacion_simple` (contextos `baseline` y `negociacion_sala_reuniones`) con **la misma mecánica interna** que `negociacion`:

- mismo pipeline core,
- misma trazabilidad,
- misma semántica de resolución de contexto,
- misma estructura de assets por contexto,
- separación solo en lo estrictamente específico del flujo.

No se hará un segundo motor paralelo: se hará **router + adapters de dominio** sobre un núcleo común.

---

## 2) Diagnóstico preciso del estado actual

1. El servicio de evaluación está acoplado a negociación porque importa y usa directamente `build_feedback_input_bundle_v1` desde `evaluacion.domains.negotiation`.  
2. El resolver de contexto de evaluación solo conoce negociación (`read_bound_context_from_session`, `resolve_negotiation_context`, `resolve_default_negotiation_context`).  
3. El extractor actual construye `DomainContext(domain="negociacion")` y lee `negotiation_canonical` / `negotiation_canonical_traces`.  
4. `DomainContext` y `DomainRubricMetadata` están tipados con `Literal["negociacion"]`, lo que impide soportar oficialmente otro flujo sin ajustar contrato interno.  
5. `conversacion_simple` ya tiene binding de sesión (`conversacion_simple_context`) y resolución oficial de contextos, por lo que puede integrarse sin inventar mecanismos nuevos.

---

## 3) Diseño objetivo (arquitectura final)

## 3.1 Núcleo común (se reutiliza)
Se mantiene sin cambios conceptuales:

- `evaluacion.engine.input_shaping`
- `evaluacion.engine.runners.*`
- `evaluacion.engine.validators`
- `evaluacion.engine.reconciliation`
- `evaluacion.engine.assembler`
- `evaluacion.storage.*`
- contrato público de reportes (`UiFeedbackReportV1`)

## 3.2 Capa de dominio (nuevo patrón común)
Crear router de dominio con un contrato único:

```python
class EvaluationDomainAdapter(Protocol):
    flow_id: str
    def build_feedback_input_bundle_v1(self, *, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1: ...
```

Implementaciones:
- `NegotiationEvaluationAdapter` (envolviendo lógica actual de negociación)
- `ConversacionSimpleEvaluationAdapter` (nuevo)

## 3.3 Estructura de assets por contexto (idéntica)
`conversacion_simple` tendrá en cada contexto oficial:

- `evaluation/core_evaluator_prompt.txt`
- `evaluation/trajectory_evaluator_prompt.txt`
- `evaluation/rubric.json`

con misma regla de fallback y `resolution_source` que negociación.

## 3.4 Resolución determinista de contexto (misma semántica)
Orden único para ambos flujos:
1. `domain_context` explícito (si viene en bundle) validado.
2. binding de sesión del flujo.
3. default oficial del flujo.
4. fallback legacy de prompts/rúbrica solo si faltan assets contextuales.

Persistencia obligatoria de: `flow_id`, `context_id`, `context_version`, `resolution_source`.

---

## 4) Plan de cambios exactos por archivo (futura implementación)

## 4.1 Contratos internos de evaluación

### Archivo: `backend/evaluacion/contracts/models.py`

### Cambio A — ampliar dominio soportado
- `DomainContext.domain`: de `Literal["negociacion"]` a `Literal["negociacion", "conversacion_simple"]`.
- `DomainRubricMetadata.domain`: mismo ajuste.

### Cambio B — conservar compatibilidad
- No tocar `schema_version` de `FeedbackInputBundleV1` ni `UiFeedbackReportV1`.
- Mantener campos existentes (`final_phase`, `finish_button_was_armed`) como opcionales, válidos aunque no apliquen en `conversacion_simple`.

### Justificación
Permite soportar ambos flujos sin romper contrato externo ni duplicar esquemas.

---

## 4.2 Router de dominio

### Archivo nuevo: `backend/evaluacion/domains/router.py`

### Contenido exacto a introducir
1. `EvaluationDomainAdapter` (Protocol).
2. `resolve_flow_id_from_state(state)`:
   - prioridad: binding negociación / binding conversacion_simple,
   - fallback: `"negociacion"` por compatibilidad legacy.
3. Registro estático:
   - `"negociacion" -> NegotiationEvaluationAdapter`
   - `"conversacion_simple" -> ConversacionSimpleEvaluationAdapter`
4. `build_feedback_input_bundle_v1(state, evaluation_id)` delegando al adapter.

### Reglas de conflicto
- Si hay bindings de ambos flujos en la misma sesión y no coinciden, lanzar error explícito (`evaluation_flow_conflict`).

---

## 4.3 Servicio de evaluación

### Archivo: `backend/evaluacion/engine/service.py`

### Cambio exacto
- Reemplazar import actual:
  - `from evaluacion.domains.negotiation import build_feedback_input_bundle_v1`
- por:
  - `from evaluacion.domains.router import build_feedback_input_bundle_v1`

### Resto
- Mantener `_run_pipeline_from_bundle` intacto.
- Mantener `artifacts`/`provenance` tal como están (ya incluyen `flow_id/context_id/context_version`).

### Impacto
- El pipeline pasa a ser multi-flujo sin alterar ensamblado, storage ni contrato API.

---

## 4.4 Adaptador de negociación (refactor sin cambio funcional)

### Archivos a tocar
- `backend/evaluacion/domains/negotiation/__init__.py`
- (opcional nuevo) `backend/evaluacion/domains/negotiation/adapter.py`

### Cambio exacto
- Exponer clase `NegotiationEvaluationAdapter` con método:
  - `build_feedback_input_bundle_v1(state, evaluation_id)`
- Implementación delega 1:1 al extractor actual.

### Nota
No cambiar semántica de negociación en esta fase; solo encapsularla detrás del contrato común.

---

## 4.5 Dominio de evaluación para conversacion_simple

### Carpeta nueva
- `backend/evaluacion/domains/conversacion_simple/`

### Archivos nuevos y responsabilidad
1. `__init__.py`
   - exporta adapter + funciones principales.
2. `context_resolver.py`
   - `resolve_evaluation_context_from_session(state)` usando:
     - `read_bound_conversacion_simple_context_from_session`
     - `resolve_conversacion_simple_context`
     - `resolve_default_conversacion_simple_context`
   - `resolve_evaluation_context_from_domain_context(domain_context)`.
3. `assets_loader.py`
   - `resolve_conversacion_simple_evaluation_assets(domain_context)`.
   - busca `context_dir/evaluation/{core,trajectory,rubric}`.
   - fallback a legacy prompts/rubric comunes de `evaluacion/prompts` (o rubrica legacy definida).
4. `extractor.py`
   - `build_feedback_input_bundle_v1(state, evaluation_id)`.
   - reconstruye turnos igual que negociación (reusar helper común).
   - `domain_context.domain = "conversacion_simple"`.
   - `flow_id/context_id/context_version` desde resolver.
   - `trace_digest` leyendo trazas propias del flujo (clave definida en fase de implementación).
5. `adapter.py`
   - clase `ConversacionSimpleEvaluationAdapter`.

### Decisión de reutilización
Mover helpers compartidos (`_pair_turns_from_history`, `_build_stats`) a módulo común para no duplicar entre extractores.

---

## 4.6 Módulo común para extractores

### Archivo nuevo: `backend/evaluacion/domains/common_extractor.py`

### Funciones a crear
- `pair_turns_from_history(state) -> list[BundleTurn]`
- `build_conversation_stats(turns) -> ConversationStats`

### Uso
- `negotiation/extractor.py` y `conversacion_simple/extractor.py` importan estas funciones.

### Resultado
Cero duplicación en lógica genérica de turnos/stats.

---

## 4.7 Assets de evaluación en contextos conversacion_simple

### Directorios nuevos
- `backend/conversacion_simple/contexts/baseline/evaluation/`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/evaluation/`

### Archivos por directorio
- `core_evaluator_prompt.txt`
- `trajectory_evaluator_prompt.txt`
- `rubric.json`

### Regla de contenido inicial
- bootstrap desde plantilla de negociación, ajustando lenguaje/criterios del flujo.
- mantener versión explícita dentro de `rubric.json`.

---

## 4.8 Carga de rúbrica por dominio

### Archivos a tocar
- `backend/evaluacion/domains/negotiation/rubric_loader.py`
- `backend/evaluacion/engine/input_shaping.py`

### Cambio exacto
- `input_shaping` dejará de asumir rúbrica solo negociación y pedirá rúbrica al adapter/dominio correspondiente.
- negociación mantiene su loader actual.
- conversacion_simple tendrá loader paralelo con mismo contrato de salida.

### Compatibilidad
- estructura de rúbrica puede mantenerse en el mismo modelo si blocks siguen siendo equivalentes.
- si cambian blocks, se define extensión mínima compatible.

---

## 4.9 Tests (exactos) a introducir/ajustar

### A. Router multi-flujo
- `backend/tests/test_evaluation_domain_router.py`
  - selecciona adapter correcto por sesión,
  - conflicto de flows en sesión -> error explícito,
  - fallback legacy -> negociación.

### B. Paridad negociación (no regresión)
- ajustar `backend/tests/test_phase6_evaluation_context_aware.py`
  - ejecutar misma suite vía router,
  - validar igualdad de salida frente a baseline anterior.

### C. conversacion_simple context-aware
- `backend/tests/test_conversacion_simple_evaluation_context_aware.py`
  - binding `baseline` / `negociacion_sala_reuniones`,
  - provenance correcto,
  - no mezcla de contextos.

### D. Assets loader conversacion_simple
- `backend/tests/test_conversacion_simple_evaluation_assets_loading.py`
  - carga contextual correcta,
  - fallback controlado,
  - `resolution_source` esperado.

### E. Aislamiento multi-flujo
- `backend/tests/test_evaluation_multiflow_context_isolation.py`
  - sesiones concurrentes con ambos flujos,
  - sin contaminación de flow/context/assets.

---

## 5) Plan por fases de ejecución (cuando autorices implementar)

### Fase 1 — Refactor seguro (infra)
1. ampliar literals en `contracts/models.py`,
2. crear `domains/router.py`,
3. encapsular negociación como adapter,
4. mantener comportamiento idéntico (golden tests).

### Fase 2 — Comunes + dominio conversacion_simple
1. extraer helpers compartidos de extractor,
2. crear carpeta `evaluacion/domains/conversacion_simple/` completa,
3. conectar adapter en router.

### Fase 3 — Assets por contexto
1. crear `evaluation/` en ambos contextos de conversacion_simple,
2. implementar `assets_loader` contextual + fallback.

### Fase 4 — End-to-end y hardening
1. suite de pruebas completa,
2. validación de trazabilidad,
3. validación de aislamiento concurrente,
4. métricas/alertas para fallback inesperado.

---

## 6) Matriz de pruebas (criterios de aceptación)

| Área | Caso | Resultado esperado |
|---|---|---|
| Router | sesión negociación | adapter negociación |
| Router | sesión conversacion_simple | adapter conversacion_simple |
| Router | conflicto bindings | error explícito |
| Contexto | `domain_context` válido | prioridad máxima |
| Contexto | sin `domain_context` | usa binding de sesión |
| Contexto | sin binding | usa default oficial |
| Assets | contextuales presentes | usa `context_evaluation_assets` |
| Assets | faltan assets | usa `legacy_fallback` visible |
| Provenance | ambos flujos | `flow_id/context_id/context_version` correcto |
| Aislamiento | sesiones paralelas | cero mezcla |
| Compatibilidad | endpoints/reportes | sin ruptura |

---

## 7) Riesgos y mitigaciones

1. **Ruptura de contrato por ampliar literals**  
   Mitigación: mantener schema y validar backward compatibility con tests de serialización.

2. **Duplicación entre extractores**  
   Mitigación: módulo común `common_extractor.py` obligatorio.

3. **Fallback silencioso de assets**  
   Mitigación: `resolution_source` persistido + tests + alerta.

4. **Confusión de flow en sesión**  
   Mitigación: detector de conflicto en router y fallo temprano.

---

## 8) Definición de éxito final

Se aprueba implementación cuando:

1. `conversacion_simple` evalúa `baseline` y `negociacion_sala_reuniones` con assets editables por contexto.
2. `negociacion` y `conversacion_simple` usan mismo pipeline + misma mecánica de resolución/context tracing.
3. No hay mezcla entre flujos/contextos en pruebas concurrentes.
4. El contrato público de evaluación permanece estable.
5. La cobertura de tests de router + context-aware + assets + aislamiento queda en verde.

---

## 9) Lista final de archivos previstos para modificar (implementación futura)

### Modificar
- `backend/evaluacion/contracts/models.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/input_shaping.py`
- `backend/evaluacion/domains/negotiation/__init__.py`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/evaluacion/domains/negotiation/rubric_loader.py`
- `backend/tests/test_phase6_evaluation_context_aware.py`

### Crear
- `backend/evaluacion/domains/router.py`
- `backend/evaluacion/domains/common_extractor.py`
- `backend/evaluacion/domains/conversacion_simple/__init__.py`
- `backend/evaluacion/domains/conversacion_simple/adapter.py`
- `backend/evaluacion/domains/conversacion_simple/context_resolver.py`
- `backend/evaluacion/domains/conversacion_simple/assets_loader.py`
- `backend/evaluacion/domains/conversacion_simple/extractor.py`
- `backend/evaluacion/domains/conversacion_simple/rubric_loader.py`
- `backend/tests/test_evaluation_domain_router.py`
- `backend/tests/test_conversacion_simple_evaluation_context_aware.py`
- `backend/tests/test_conversacion_simple_evaluation_assets_loading.py`
- `backend/tests/test_evaluation_multiflow_context_isolation.py`
- `backend/conversacion_simple/contexts/baseline/evaluation/core_evaluator_prompt.txt`
- `backend/conversacion_simple/contexts/baseline/evaluation/trajectory_evaluator_prompt.txt`
- `backend/conversacion_simple/contexts/baseline/evaluation/rubric.json`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/evaluation/core_evaluator_prompt.txt`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/evaluation/trajectory_evaluator_prompt.txt`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/evaluation/rubric.json`

