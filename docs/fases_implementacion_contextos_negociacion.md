# Fases de implementación para llevar `negociacion` a `motor estable + contextos`

## 1. Propósito del documento maestro

Este documento organiza la ejecución real de la migración hacia el modelo:

- `backend/negociacion/` como motor estable;
- contextos/casos como bundles de prompts + assets JSON + evaluación;
- `context_id` fijo en sesión;
- URL pública capaz de resolver contexto;
- evaluación y optimizer context-aware;
- preservación estricta del comportamiento actual del caso baseline.

No es un resumen conceptual: es el mapa de trabajo para decidir orden, dependencias y criterios de paso entre fases.

---

## 2. Orden de fases recomendado

1. **Fase 01 — baseline oficial de contexto**
2. **Fase 02 — resolución de contexto en runtime**
3. **Fase 03 — fijación de contexto en sesión**
4. **Fase 04 — superficie pública y URL de contexto**
5. **Fase 05 — trazas context-aware**
6. **Fase 06 — evaluación context-aware**
7. **Fase 07 — optimizer context-aware**
8. **Fase 08 — segundo contexto oficial**

Este orden está pensado para que cada fase:

- introduzca solo una clase de responsabilidad nueva;
- mantenga compatibilidad hacia atrás mientras sea necesario;
- y nunca exija cambiar la forma de negociar del baseline actual.

---

## 3. Dependencias entre fases

## Fase 01 -> Fase 02

La Fase 02 depende de la Fase 01 porque primero hace falta una identidad oficial de contexto baseline antes de redirigir el runtime hacia una resolución contextual.

## Fase 02 -> Fase 03

La Fase 03 depende de la Fase 02 porque no se puede fijar bien un `context_id` en sesión si el runtime todavía no tiene una fuente oficial y unívoca para resolver ese contexto.

## Fase 03 -> Fase 04

La Fase 04 depende de la Fase 03 porque la URL pública solo es segura si la sesión ya puede persistir la identidad contextual y evitar mezclas.

## Fase 03 -> Fase 05

La Fase 05 depende de la Fase 03 porque las trazas deben reflejar el contexto realmente fijado, no una inferencia parcial.

## Fase 03 + Fase 05 -> Fase 06

La evaluación context-aware necesita:

- identidad contextual persistida,
- y trazabilidad/contexto efectivo visible.

## Fase 03 + Fase 05 -> Fase 07

El optimizer context-aware necesita:

- contexto oficial base,
- sesiones con contexto fijo,
- y trazas capaces de distinguir baseline vs overrides.

## Fase 06 + Fase 07 -> Fase 08

No conviene abrir un segundo contexto oficial hasta que:

- runtime,
- sesión,
- trazas,
- evaluación,
- y optimizer

puedan operar sin ambigüedad contextual.

---

## 4. Qué riesgo mitiga cada fase

## Fase 01

Mitiga la ausencia de una identidad oficial del caso actual y la convivencia implícita entre “bundle real” y “bundle conceptual”.

## Fase 02

Mitiga la divergencia entre código del motor y origen real de prompts/assets.

## Fase 03

Mitiga contaminación entre contextos en sesión y arrastre de canonical state / OpenAI thread de un contexto a otro.

## Fase 04

Mitiga diferencias entre lo que la URL pública pretende representar y el contexto realmente usado por backend.

## Fase 05

Mitiga opacidad diagnóstica: conversaciones correctas pero sin identidad contextual demostrable.

## Fase 06

Mitiga evaluación con assets equivocados o informes producidos sin saber qué contexto se evaluó.

## Fase 07

Mitiga que el optimizer funcione como vía paralela de bundles y no como espejo del runtime público.

## Fase 08

Mitiga el riesgo de abrir múltiples contextos antes de cerrar la infraestructura mínima de identidad y trazabilidad.

---

## 5. Invariantes globales que no pueden romperse en ninguna fase

Estas reglas deben cumplirse en todas las fases:

1. El **prompt efectivo** del caso actual no puede cambiar mientras siga siendo el baseline.
2. El **payload efectivo** de `persona.json`, `negotiation_brief.json`, `phase_cards.json` y `phase_classifier_card.json` del baseline no puede cambiar.
3. El **orden del pipeline** sigue siendo el mismo.
4. El **shape observable** de `CanonicalState`, `NegotiationState`, `PlannerState`, `SceneState` y `NegotiationUiState` no cambia salvo incorporación estrictamente compatible de metadatos contextuales.
5. La semántica de `finish_button_armed` no cambia.
6. La API pública existente debe seguir funcionando con el baseline.
7. La evaluación visible del baseline no debe cambiar hasta la fase que la vuelva explícitamente context-aware sin alterar sus prompts/rúbrica efectivas.
8. El optimizer baseline debe seguir pudiendo ejecutar el mismo caso actual aunque todavía no elija otro contexto explícitamente.

---

## 6. Qué partes del repo siguen siendo “motor”

Se mantienen como motor estable:

- `backend/negociacion/pipeline.py`
- `backend/negociacion/orchestration/`
- `backend/negociacion/nodes/`
- `backend/negociacion/state/` como shape de estado
- `backend/negociacion/guards/`
- `backend/negociacion/traces/`
- `backend/sessions/` como infraestructura base de sesión
- pipeline base de `backend/evaluacion/engine/`
- superficies API existentes de `backend/interfaz_usuario/` y `backend/negociacion/optimizador/`

---

## 7. Qué partes pasan a ser “contexto”

Se consolidan como contexto:

- prompts del flow de negociación;
- `persona.json`;
- `negotiation_brief.json`;
- `phase_cards.json`;
- `phase_classifier_card.json`;
- prompts/rúbrica evaluativos por contexto;
- metadatos mínimos del caso (`context_id`, `context_version`, `public_slug`, etc.);
- datasets/fixtures ligados a un contexto concreto.

---

## 8. Qué partes seguirán mixtas temporalmente

Durante la migración seguirán mixtas:

- `backend/negociacion/orchestration/flow_config.py`, porque seguirá siendo motor pero pasará a consumir resolución contextual;
- `backend/negociacion/state/canonical_state.py`, porque conserva el shape del estado pero dejará de ser la fuente directa de rutas hardcodeadas;
- `backend/interfaz_usuario/services.py`, porque seguirá siendo entrypoint de turnos pero empezará a fijar contexto;
- `backend/evaluacion/domains/negotiation/extractor.py`, porque seguirá extrayendo bundle evaluativo desde sesión pero luego incorporará identidad contextual;
- `backend/negociacion/optimizador/services.py` y `experiments_bridge.py`, porque mantendrán overrides pero pasarán a operar sobre un contexto oficial base.

---

## 9. Criterio para pasar de una fase a la siguiente

## Paso 01 -> 02

Solo si ya existe un contexto baseline oficial documentado y estable.

## Paso 02 -> 03

Solo si runtime y canonical state resuelven exactamente el mismo bundle baseline.

## Paso 03 -> 04

Solo si toda sesión nueva de negociación queda fijada a un `context_id` sin romper compatibilidad.

## Paso 04 -> 05

Solo si la entrada pública y backend resuelven el mismo contexto sin ambigüedad.

## Paso 05 -> 06

Solo si las trazas ya pueden identificar contexto baseline vs contexto con overrides.

## Paso 06 -> 07

Solo si la evaluación ya consume identidad contextual oficial sin cambiar el baseline visible.

## Paso 07 -> 08

Solo si optimizer, runtime, sesión, trazas y evaluación son context-aware sobre el baseline y comparables entre sí.

---

## 10. Corte mínimo recomendable para una primera entrega real

La primera entrega real recomendable es:

- Fase 01 completa
- Fase 02 completa
- Fase 03 mínima
- Fase 05 mínima

### Motivo

Ese corte ya deja preparado lo esencial:

- baseline oficial;
- resolución contextual del runtime;
- contexto fijo en sesión;
- contexto visible en trazas.

Y todavía evita tocar demasiado pronto:

- frontend público final por URL,
- evaluación completa context-aware,
- optimizer completo context-aware,
- y segundo contexto oficial.

---

## 11. Documentos individuales de fase

- `docs/fase_01_baseline_oficial_contexto.md`
- `docs/fase_02_resolucion_contexto_runtime.md`
- `docs/fase_03_fijacion_contexto_en_sesion.md`
- `docs/fase_04_superficie_publica_y_url_contexto.md`
- `docs/fase_05_trazas_context_aware.md`
- `docs/fase_06_evaluacion_context_aware.md`
- `docs/fase_07_optimizer_context_aware.md`
- `docs/fase_08_segundo_contexto_oficial.md`

---

## 12. Regla ejecutiva final

Si en algún punto una fase obliga a cambiar:

- el prompt efectivo del baseline,
- la forma de negociar del baseline,
- el shape observable del estado,
- la lógica de `finish_button_armed`,
- o el comportamiento del optimizer/evaluación baseline,

esa fase está mal acotada y debe dividirse o rediseñarse antes de ejecutarse.
