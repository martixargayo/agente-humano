# Ejecución de Fase 02 — resolución de contexto runtime

## Qué cambió exactamente

Se introdujo una capa mínima de resolución contextual interna para `negociacion` y el runtime baseline pasó a construir su config y sus defaults de estado usando esa misma resolución oficial.

El alcance de la fase fue deliberadamente pequeño:

- se creó un modelo mínimo de contexto resuelto;
- se creó un resolver conservador con fallback explícito a legacy;
- `build_negotiation_pipeline_config()` pasó a resolver `prompts_dir` desde el baseline oficial;
- `canonical_state.py` dejó de construir por su cuenta rutas legacy hardcodeadas para `persona.json` y `negotiation_brief.json` y pasó a usar la misma resolución baseline.

## Qué estaba ya bien

Antes de este ajuste final ya estaban bien resueltos estos puntos:

- `build_negotiation_pipeline_config()` ya tomaba `prompts_dir` desde `resolve_default_negotiation_context()`;
- `canonical_state.py` ya tomaba `persona_path` desde `resolve_default_negotiation_context()`;
- `canonical_state.py` ya tomaba `negotiation_brief_path` desde `resolve_default_negotiation_context()`.

Eso significaba que los `.txt` del flow y los defaults principales del estado ya compartían la misma identidad baseline.

## Qué faltaba exactamente

Quedaba una incompletitud real en `flow_config.py`:

- `_load_phase_cards()` seguía construyendo `Path(prompts_dir) / "phase_cards.json"`;
- `_load_phase_classifier_card()` seguía construyendo `Path(prompts_dir) / "phase_classifier_card.json"`.

Eso era incorrecto para la estructura oficial del baseline porque:

- los prompts `.txt` viven en `prompts/`;
- `phase_cards.json` y `phase_classifier_card.json` viven en `assets/`.

Mientras esos loaders derivaran los JSON desde `prompts_dir`, la Fase 2 no quedaba cerrada de verdad.

## Archivos tocados

### Nuevos

- `backend/negociacion/contexts/models.py`
- `backend/negociacion/contexts/resolver.py`
- `backend/tests/test_phase2_context_runtime_resolution.py`
- `backend/scripts/check_phase2_context_runtime_resolution.py`
- `docs/ejecucion_fase_02_resolucion_contexto_runtime.md`

### Modificados

- `backend/negociacion/contexts/__init__.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/state/canonical_state.py`

## Cómo se resuelve ahora el baseline

La resolución baseline queda centralizada en `backend/negociacion/contexts/resolver.py`.

Ruta normal:
- intenta resolver `backend/negociacion/contexts/baseline_current/manifest.json`
- valida la existencia del bundle baseline oficial
- devuelve rutas efectivas a:
  - `prompts_dir`
  - `persona_path`
  - `negotiation_brief_path`
  - `phase_cards_path`
  - `phase_classifier_card_path`

Ruta de fallback:
- si el baseline oficial no existe, falla o está incompleto,
- el resolver cae explícitamente a las rutas legacy actuales bajo `backend/negociacion/prompts/`.

## Cómo se corrigió el punto faltante

Se mantuvo el cambio mínimo y conservador:

- `ResolvedNegotiationContext` ya exponía explícitamente:
  - `prompts_dir`
  - `persona_path`
  - `negotiation_brief_path`
  - `phase_cards_path`
  - `phase_classifier_card_path`
- `flow_config.py` ahora usa una resolución explícita de assets para:
  - `_load_phase_cards()`
  - `_load_phase_classifier_card()`

La lógica quedó así:

- si `prompts_dir` coincide con el baseline runtime resuelto, esos loaders usan:
  - `resolved_context.phase_cards_path`
  - `resolved_context.phase_classifier_card_path`
- si el baseline oficial falla y el runtime cae a legacy, esos loaders usan:
  - `backend/negociacion/prompts/phase_cards.json`
  - `backend/negociacion/prompts/phase_classifier_card.json`
- si en algún punto se inyecta un `prompts_dir` ajeno a esos dos casos, se preserva la compatibilidad heredada derivando desde ese directorio.

## Cómo se evitó divergencia entre runtime y canonical_state

Antes de esta fase había un riesgo claro:

- `flow_config.py` y el runtime podían terminar leyendo una fuente,
- mientras `canonical_state.py` seguía leyendo por su cuenta otra ruta hardcodeada.

Después de esta fase:

- `flow_config.py` obtiene `prompts_dir` desde `resolve_default_negotiation_context()`;
- `flow_config.py` obtiene además `phase_cards` y `phase_classifier_card` desde paths explícitos del mismo contexto resuelto;
- `canonical_state.py` obtiene `persona_path` y `negotiation_brief_path` desde esa misma resolución baseline.

Eso alinea runtime y defaults del estado sobre una sola identidad interna de baseline.

## Qué fallback se dejó

Se dejó fallback conservador y explícito a legacy dentro del resolver.

No se trata de un fallback silencioso opaco:
- el contexto resuelto informa `resolution_source`
- y si el baseline oficial falta o falla, el resolver devuelve un baseline funcional apoyado en las rutas legacy existentes.

## Qué NO se tocó

No se tocaron:

- `backend/sessions/state.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario_app/*`
- `backend/evaluacion/engine/*`
- `backend/evaluacion/domains/negotiation/*`
- `backend/negociacion/optimizador/*`

Tampoco se introdujo todavía:

- `context_id` en sesión
- URL pública contextual
- trazas context-aware
- evaluación context-aware
- optimizer context-aware

## Por qué el comportamiento sigue siendo el mismo

La fase no cambia cómo negocia el sistema porque:

1. el baseline oficial contiene el mismo bundle que el legacy actual;
2. el runtime resuelve ahora ese baseline también para los JSON de fase, no solo para los prompts `.txt`;
3. si algo falla en el baseline oficial, el resolver vuelve a legacy;
4. no cambió el orden del pipeline;
5. no cambió el shape de `CanonicalState`;
6. no cambió la semántica de `NegotiationState`;
7. no cambió `finish_button_armed`;
8. no cambió la API pública;
9. no cambió evaluación visible;
10. no cambió optimizer visible.

## Por qué ahora sí queda cerrada la Fase 2

Ahora la identidad baseline oficial resuelta en runtime cubre de forma alineada:

- `prompts_dir`
- `persona_path`
- `negotiation_brief_path`
- `phase_cards_path`
- `phase_classifier_card_path`

Y quedan alineados sobre la misma resolución:

- `flow_config.py`
- `canonical_state.py`

Con eso ya no queda ninguna lectura principal del baseline derivada implícitamente desde una ruta equivocada de `prompts/` hacia archivos que realmente viven en `assets/`.

## Qué queda preparado para la Fase 3

Queda preparado que una fase posterior fije explícitamente en sesión la identidad del baseline ya resuelto.

Pero en esta fase eso todavía no se implementa: solo se unifica internamente la resolución baseline del runtime.
