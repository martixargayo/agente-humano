# Fase 01 — baseline oficial de contexto

## 1. Propósito exacto de la fase

Esta fase convierte el caso actual en el **contexto baseline oficial** del flow `negociacion`.

Su función no es cambiar cómo carga el runtime hoy, sino crear una representación oficial y estable de “qué bundle exacto constituye el comportamiento actual”.

Va primero porque sin baseline oficial no puede demostrarse después que la migración preserva comportamiento.

---

## 2. Qué se cambia exactamente

Se introduce solo documentación/estructura de contexto oficial para el caso actual:

- raíz oficial para contextos de `negociacion`;
- un contexto baseline único equivalente al bundle actual;
- un `manifest.json` mínimo para identificarlo;
- organización explícita de prompts, assets y evaluación del baseline;
- documentación de correspondencia 1:1 entre contenido legacy y contenido baseline.

No se cambia todavía el runtime productivo.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/negociacion/prompts/` (solo como fuente a reflejar/documentar)
- `backend/evaluacion/prompts/` (solo como fuente a reflejar/documentar)
- `backend/evaluacion/domains/negotiation/rubrics/negotiation_rubric_v1.json`
- `docs/propuesta_organizacion_contextos_negociacion.md`
- `docs/plan_implementacion_contextos_negociacion.md`

### Archivos nuevos a crear

- `backend/negociacion/contexts/baseline_current/manifest.json`
- `backend/negociacion/contexts/baseline_current/prompts/planner_prompt.txt`
- `backend/negociacion/contexts/baseline_current/prompts/executor_prompt.txt`
- `backend/negociacion/contexts/baseline_current/prompts/summarizer_prompt.txt`
- `backend/negociacion/contexts/baseline_current/prompts/phase_classifier_prompt.txt`
- `backend/negociacion/contexts/baseline_current/assets/persona.json`
- `backend/negociacion/contexts/baseline_current/assets/negotiation_brief.json`
- `backend/negociacion/contexts/baseline_current/assets/phase_cards.json`
- `backend/negociacion/contexts/baseline_current/assets/phase_classifier_card.json`
- `backend/negociacion/contexts/baseline_current/evaluation/core_evaluator_prompt.txt`
- `backend/negociacion/contexts/baseline_current/evaluation/trajectory_evaluator_prompt.txt`
- `backend/negociacion/contexts/baseline_current/evaluation/rubric.json`
- `docs/baseline_contexto_negociacion_actual.md`

---

## 4. Cambios exactos archivo por archivo

### `backend/negociacion/prompts/*`

- **Responsabilidad hoy:** bundle efectivo real del runtime.
- **Cambio:** no se modifica su uso en esta fase.
- **Tratamiento:** se conserva como fuente legacy mientras se crea un espejo oficial del baseline.
- **Compatibilidad:** total; siguen siendo la única fuente consumida por runtime.

### `backend/evaluacion/prompts/*` y `backend/evaluacion/domains/negotiation/rubrics/negotiation_rubric_v1.json`

- **Responsabilidad hoy:** assets evaluativos efectivos del baseline.
- **Cambio:** no cambian de uso aún.
- **Tratamiento:** se reflejan en el contexto baseline como copia o espejo controlado.
- **Compatibilidad:** total.

### `backend/negociacion/contexts/baseline_current/manifest.json`

- **Responsabilidad nueva:** declarar la identidad oficial del baseline.
- **Contenido esperado:** `context_id`, `flow_id`, `context_version`, `public_slug`, `status`, referencias a prompts/assets/evaluation.
- **Compatibilidad:** no consumido aún por runtime.

### `docs/baseline_contexto_negociacion_actual.md`

- **Responsabilidad nueva:** documentar qué archivos legacy concretos equivalen al contexto baseline y qué checks garantizan su igualdad.
- **Compatibilidad:** solo documental.

### `docs/plan_implementacion_contextos_negociacion.md` y docs relacionados

- **Responsabilidad hoy:** guiar estrategia general.
- **Cambio:** actualizar referencias para que el baseline se nombre de forma explícita y operativa.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  negociacion/
    contexts/
      baseline_current/
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

docs/
  baseline_contexto_negociacion_actual.md
```

---

## 6. Qué NO se toca todavía

- `backend/negociacion/pipeline.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/state/canonical_state.py`
- `backend/interfaz_usuario/`
- `backend/interfaz_usuario_app/`
- `backend/evaluacion/engine/`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/negociacion/optimizador/`
- `backend/sessions/state.py`

---

## 7. Cómo se garantiza equivalencia funcional

- el runtime sigue leyendo el bundle legacy actual;
- el baseline nuevo solo refleja ese bundle y no sustituye su consumo;
- no cambian prompts efectivos;
- no cambian JSON efectivos;
- no cambia el state observable;
- no cambia `finish_button_armed`;
- no cambia API pública;
- no cambia evaluación visible;
- no cambia optimizer baseline.

---

## 8. Riesgos específicos de la fase

- crear un baseline que no sea exactamente igual al bundle actual;
- introducir un `manifest.json` con naming que luego no cuadre con resolver futuro;
- dejar sin documentar si el baseline es copia física o espejo temporal.

---

## 9. Validaciones y checks recomendados

- diff de contenido entre prompts/assets legacy y baseline oficial;
- checklist de igualdad 1:1 para evaluación baseline;
- verificación de que ningún archivo de runtime consume aún la nueva raíz de contextos.

---

## 10. Condición de salida

Existe un contexto baseline oficial completo y documentado, equivalente al comportamiento actual, sin haber cambiado todavía la fuente efectiva del runtime.

---

## 11. Rollback / compatibilidad

Rollback trivial: si algo está mal en el baseline oficial, se corrige o se elimina la nueva carpeta sin impacto en runtime porque el runtime aún no la consume.
