# Propuesta de organización física de contextos de `negociacion`

## Objetivo del diseño

Organizar en el repo, **solo a nivel de documentación y propuesta**, una estructura donde:

- el motor de `negociacion` siga siendo estable;
- cada caso/contexto tenga su propio bundle;
- la URL pública seleccione un contexto;
- la sesión quede fijada a ese contexto;
- y evaluación/optimizer puedan resolver el mismo contexto sin ambigüedad.

No se busca diseñar un plugin framework ni una plataforma abstracta. Solo ordenar bien una realidad concreta del repo.

---

## 1. Criterio rector: separar “motor” de “contexto”

## Motor estable

Debería seguir viviendo en el área actual de runtime:

- `backend/negociacion/pipeline.py`
- `backend/negociacion/orchestration/`
- `backend/negociacion/state/`
- `backend/negociacion/nodes/`
- `backend/negociacion/guards/`
- `backend/negociacion/traces/`

Eso es la maquinaria reusable del flow.

## Contexto

Debería agrupar solo lo que define un caso concreto sin cambiar la maquinaria:

- prompts del flujo;
- JSONs estáticos del caso;
- assets de phase system del caso;
- assets de evaluación del caso;
- metadatos mínimos del caso.

---

## 2. Opciones de estructura

## Opción A — `backend/negociacion/contexts/<context_id>/...`

Ejemplo conceptual:

```text
backend/
  negociacion/
    contexts/
      mustang/
      salario/
      proveedor/
```

### Ventajas

- `contexts` comunica bien que son variantes del mismo flow.
- Evita sugerir que cada carpeta es un flow distinto.
- Encaja bien con tu hipótesis: mismo motor, distintos context packs.

### Inconvenientes

- Puede sonar demasiado genérico si en la práctica cada carpeta es un “caso” concreto.

## Opción B — `backend/negociacion/cases/<case_id>/...`

### Ventajas

- Más legible para equipos que piensan en “casos” pedagógicos o de negocio.
- Muy natural si cada URL pública es una actividad/caso.

### Inconvenientes

- Puede inducir a pensar que “case” es la unidad principal del sistema, cuando en realidad la unidad principal sigue siendo el flow `negociacion`.
- Es ligeramente peor si quieres admitir variantes del mismo caso (versiones, idiomas, etc.) sin duplicar semántica.

## Opción C — mantener `prompts/` global y añadir overlays dispersos

Ejemplo:

- prompts base en `backend/negociacion/prompts/`
- overrides por caso en otra carpeta
- evaluación por caso en otra tercera carpeta

### Ventajas

- mínima disrupción conceptual.

### Inconvenientes

- fragmenta el pack contextual;
- dificulta trazabilidad;
- empeora la legibilidad de “qué define exactamente el contexto X”.

## Recomendación

La opción más limpia para este repo es:

## **`backend/negociacion/contexts/<context_id>/`**

porque subraya que seguimos dentro de **un mismo flow**.

---

## 3. Árbol propuesto

```text
backend/
  negociacion/
    contexts/
      mustang/
        manifest.json
        prompts/
          planner_prompt.txt
          executor_prompt.txt
          summarizer_prompt.txt
          phase_classifier_prompt.txt
        assets/
          persona.json
          negotiation_brief.json
          phase_cards.json
          phase_classifier_card.json
        evaluation/
          core_evaluator_prompt.txt
          trajectory_evaluator_prompt.txt
          rubric.json
          fixtures/
            *.json
            *.jsonl

      salario/
        manifest.json
        prompts/
        assets/
        evaluation/

      proveedor/
        manifest.json
        prompts/
        assets/
        evaluation/
```

---

## 4. Qué pondría dentro de cada carpeta

## 4.1. `manifest.json`

No como meta-sistema complejo, sino como descriptor mínimo del contexto.

Contenido sugerido:

- `context_id`
- `flow_id: "negociacion"`
- `title`
- `public_slug`
- `status` (`draft`, `active`, `deprecated`)
- `default_language`
- `evaluation_profile`
- `context_version`

### Por qué sí compensa

Aunque en teoría podría inferirse todo por nombres de archivos, un manifest mínimo ayuda a:

- resolver la URL pública;
- fijar la identidad de sesión;
- versionar contexto;
- y trazar qué pack se cargó realmente.

## 4.2. `prompts/`

Aquí pondría únicamente los cuatro prompts del runtime conversacional:

- `planner_prompt.txt`
- `executor_prompt.txt`
- `summarizer_prompt.txt`
- `phase_classifier_prompt.txt`

## 4.3. `assets/`

Aquí pondría los JSONs fijos del caso:

- `persona.json`
- `negotiation_brief.json`
- `phase_cards.json`
- `phase_classifier_card.json`

Separarlos de `prompts/` mejora claridad:

- texto instructivo por un lado,
- estado/contexto declarativo por otro.

## 4.4. `evaluation/`

Aquí pondría lo específico de evaluación del caso:

- `core_evaluator_prompt.txt`
- `trajectory_evaluator_prompt.txt`
- `rubric.json`
- `fixtures/` o datasets de ejemplo por caso

Eso evita dejar la evaluación “medio global y medio contextual”.

---

## 5. Qué seguiría siendo motor y qué sería contexto

## Seguiría siendo motor

- contratos de entrada/salida de nodos;
- `NegotiationTurnConfig`;
- `CanonicalState` y su shape;
- `NegotiationState`, `PlannerState`, `SceneState`, `NegotiationUiState`;
- `NegotiationPhase` enum;
- política de guardrails;
- builders de traces;
- entry contracts;
- orquestación general del turno;
- session handling base;
- pipeline base de evaluación.

## Sería contexto

- identidad y voz (`persona.json`);
- brief privado del caso (`negotiation_brief.json`);
- phase cards y card del clasificador;
- prompts de memory/planner/executor/phase classifier;
- prompts y rúbrica de evaluación;
- fixtures de evaluación y optimizer ligados al caso;
- copy pública del caso si se decide exponerla en UI.

---

## 6. Cómo conviviría con el repo actual

## 6.1. Mantener un contexto por defecto

Durante la transición, tendría sentido conservar el contexto actual como referencia base, por ejemplo:

```text
backend/negociacion/contexts/default/
```

o directamente:

```text
backend/negociacion/contexts/mustang/
```

si el caso actual ya está suficientemente identificado.

## 6.2. Evitar coexistencia prolongada de dos verdades

No recomendaría una convivencia larga entre:

- `backend/negociacion/prompts/` como bundle oficial,
- y además `backend/negociacion/contexts/...` como segundo bundle.

Como fase transitoria puede tolerarse, pero a nivel conceptual conviene que el repo tenga una única fuente de verdad para el bundle contextual.

## 6.3. Evaluación y optimizer deberían resolver desde el mismo árbol

La propuesta es más sólida si:

- runtime,
- evaluation,
- y optimizer

leen su contexto desde la misma raíz conceptual, aunque luego cada uno consuma subconjuntos distintos.

---

## 7. Organización recomendada de prompts, JSONs y evaluación

## Recomendación principal

### `backend/negociacion/contexts/<context_id>/prompts/`

Para instrucciones del flujo.

### `backend/negociacion/contexts/<context_id>/assets/`

Para JSONs de identidad/brief/fases.

### `backend/negociacion/contexts/<context_id>/evaluation/`

Para prompts, rúbrica y fixtures evaluativos del mismo contexto.

### Razón

Esta estructura hace visible algo muy valioso:

> “Todo lo que hace especial al contexto `mustang` vive junto.”

Y al mismo tiempo deja intacto el mensaje arquitectónico más importante:

> “Todo eso se ejecuta sobre el mismo motor `negociacion`.”

---

## 8. Papel de la URL pública en la resolución del contexto

La URL pública debería ser la **entrada declarativa** al contexto, no la fuente persistente de verdad durante toda la conversación.

## Papel recomendado de la URL

- resolver el `context_id` inicial;
- bootstrapear sesión con ese `context_id`;
- impedir que una sesión abierta con un contexto se use accidentalmente con otro.

## Regla recomendada

- La URL elige el contexto al entrar.
- La sesión guarda ese contexto.
- Los turnos posteriores usan el contexto guardado en sesión, no el inferido de nuevo “por si acaso”.

Eso evita mezclas cuando el usuario refresca, comparte enlaces o abre varias pestañas.

---

## 9. Papel del optimizer en esta organización

El optimizer debería verse como una **superficie de experimentación sobre un contexto base oficial**.

## Base oficial

- `context_id`
- `context_version`
- bundle oficial resuelto

## Encima de eso

- overrides de prompt;
- overrides de assets;
- pruebas sandbox;
- comparaciones de trazas;
- guardado de casos.

Lo importante es que el optimizer no sustituya la identidad del contexto, sino que opere “sobre” ella.

---

## 10. Recomendación final de organización

La propuesta más coherente con este repo es:

1. tratar `negociacion` como **flow estable**;
2. introducir una raíz explícita `backend/negociacion/contexts/`;
3. modelar cada caso como una carpeta autocontenida;
4. separar dentro de ella `prompts/`, `assets/` y `evaluation/`;
5. usar un `manifest.json` mínimo para identidad y resolución;
6. hacer que la URL pública resuelva un `context_id` y que la sesión lo fije.

No hace falta un framework abstracto. Hace falta una estructura simple y explícita donde el repo diga claramente:

- qué es motor,
- qué es contexto,
- y qué es evaluación del contexto.
