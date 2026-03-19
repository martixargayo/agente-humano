# Ejecución Fase 06 — evaluación context-aware

## Qué se cambió exactamente

Se hizo context-aware la resolución de prompts evaluativos y rúbrica del dominio `negociacion`, usando el contexto oficial ya fijado en sesión y manteniendo equivalencia práctica total para `baseline_current`.

## Archivos tocados

- `backend/evaluacion/domains/negotiation/context_resolver.py`
- `backend/evaluacion/domains/negotiation/assets_loader.py`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/evaluacion/domains/negotiation/rubric_loader.py`
- `backend/evaluacion/domains/negotiation/__init__.py`
- `backend/evaluacion/engine/input_shaping.py`
- `backend/evaluacion/engine/runners/core_runner.py`
- `backend/evaluacion/engine/runners/trajectory_runner.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/demo_adapter.py`
- `backend/evaluacion/contracts/models.py`
- `backend/tests/test_phase6_evaluation_context_aware.py`
- `backend/scripts/check_phase6_evaluation_context_aware.py`
- `docs/ejecucion_fase_06_evaluacion_context_aware.md`

## Cómo se resuelven ahora prompts y rúbrica

1. el extractor obtiene `flow_id`, `context_id` y `context_version` desde la sesión ligada;
2. esos campos viajan en `bundle.domain_context`;
3. runners y rubric loader resuelven assets desde `backend/negociacion/contexts/<context_id>/evaluation/...`;
4. si falta binding o falla la resolución contextual, caen al baseline actual con fallback legacy conservador.

## Dónde viajan `flow_id/context_id/context_version`

- en `DomainContext` dentro de `FeedbackInputBundleV1`;
- en `TrajectoryRunnerInputV1`;
- en `Provenance` del informe final;
- y en artifacts del job de evaluación.

## Qué no se tocó

- prompts del runtime conversacional
- JSON del runtime
- pipeline bundle -> core -> trajectory -> reconciliation -> report
- scoring visible baseline
- wording visible del informe baseline
- frontend/UI/polling
- optimizer context-aware completo

## Por qué sigue siendo equivalente para `baseline_current`

Porque los prompts y la rúbrica resueltos contextualmente para baseline_current son equivalentes a los legacy actuales, y el pipeline sigue ejecutándose igual.

## Qué falta todavía para Fase 7 y Fase 8

- Fase 7: optimizer context-aware completo
- Fase 8: segundo contexto oficial y expansión multi-context real

En esta fase no se implementó nada de eso.
