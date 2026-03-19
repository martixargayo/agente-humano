# Ejecución de Fase 01 — baseline oficial de contexto

## Qué se creó

Se creó la raíz oficial de contextos para `negociacion` sin redirigir todavía ningún consumer productivo:

```text
backend/negociacion/contexts/
backend/negociacion/contexts/__init__.py
backend/negociacion/contexts/baseline_current/
```

Dentro de `baseline_current/` se creó la estructura oficial del baseline actual:

```text
backend/negociacion/contexts/baseline_current/
  manifest.json
  prompts/
  assets/
  evaluation/
```

## Qué archivos legacy se reflejaron 1:1

### Prompts del flujo

Copiados sin reinterpretación desde `backend/negociacion/prompts/`:

- `planner_prompt.txt`
- `executor_prompt.txt`
- `summarizer_prompt.txt`
- `phase_classifier_prompt.txt`

### Assets JSON del contexto

Copiados sin reinterpretación desde `backend/negociacion/prompts/`:

- `persona.json`
- `negotiation_brief.json`
- `phase_cards.json`
- `phase_classifier_card.json`

### Assets de evaluación baseline

Copiados sin reinterpretación desde las rutas legacy efectivas del baseline:

- `backend/evaluacion/prompts/core_evaluator_prompt.txt`
- `backend/evaluacion/prompts/trajectory_evaluator_prompt.txt`
- `backend/evaluacion/domains/negotiation/rubrics/negotiation_rubric_v1.json`

En el baseline oficial quedaron reflejados como:

- `backend/negociacion/contexts/baseline_current/evaluation/core_evaluator_prompt.txt`
- `backend/negociacion/contexts/baseline_current/evaluation/trajectory_evaluator_prompt.txt`
- `backend/negociacion/contexts/baseline_current/evaluation/rubric.json`

## Manifest creado

Se añadió `backend/negociacion/contexts/baseline_current/manifest.json` con metadatos mínimos:

- `flow_id`
- `context_id`
- `title`
- `public_slug`
- `status`
- `context_version`
- referencias simples a `prompts/`, `assets/` y `evaluation/`

No se añadió lógica nueva ni se convirtió esta fase en un framework.

## Qué equivalencias se blindaron

La fase deja blindada la equivalencia entre baseline oficial y legacy para:

- prompts del flujo
- JSONs del contexto
- prompts evaluativos
- rúbrica baseline

La validación se hace con checks automatizados que comparan:

- igualdad textual de prompts
- igualdad estructural de JSONs
- parseo correcto del manifest
- existencia de la estructura esperada
- ausencia de rewiring productivo a la nueva raíz

## Qué NO se tocó

No se modificaron consumers productivos del runtime ni de la superficie pública. En particular, no se tocaron:

- `backend/negociacion/pipeline.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/state/canonical_state.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/index.html`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/assembler.py`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/negociacion/optimizador/services.py`

Tampoco se introdujeron todavía:

- resolver de contexto
- `context_id` en sesión
- URL contextual pública
- trazas context-aware
- evaluación context-aware
- optimizer context-aware

## Por qué esta fase no cambia comportamiento

No cambia comportamiento porque:

1. el runtime sigue leyendo exactamente las mismas rutas legacy que antes;
2. los archivos nuevos son reflejos del baseline actual y no sustituyen consumidores;
3. no se modificaron prompts efectivos;
4. no se modificaron JSONs efectivos;
5. no se modificó el runtime de negociación;
6. no se modificó la evaluación efectiva;
7. no se modificó el optimizer productivo;
8. no se modificó ninguna superficie pública de entrada.

## Qué queda preparado para la Fase 2

Queda preparado un baseline oficial sobre el que la Fase 2 podrá:

- introducir resolución de contexto en runtime;
- apuntar el runtime al baseline oficial;
- y comparar equivalencia contra las rutas legacy actuales.

Esa siguiente fase podrá hacerse con menos riesgo porque ya existe un bundle baseline oficial verificable y testado.
