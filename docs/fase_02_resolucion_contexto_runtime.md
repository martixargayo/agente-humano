# Fase 02 — resolución de contexto en runtime

## 1. Propósito exacto de la fase

Esta fase hace que el runtime de `negociacion` pueda ejecutar el baseline a través de una **resolución oficial de contexto**, en vez de depender implícitamente de rutas globales dispersas.

Va aquí y no antes porque primero hacía falta un baseline oficial estable al que apuntar.

---

## 2. Qué se cambia exactamente

Se introduce una capa mínima de resolución contextual para el runtime.

### Objetivo técnico

Unificar en una sola fuente:

- `prompts_dir` del flow;
- paths de `persona.json` y `negotiation_brief.json` usados al construir el canonical state;
- paths de `phase_cards.json` y `phase_classifier_card.json` usados por la orquestación;
- metadatos del contexto baseline activo.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/negociacion/pipeline.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/state/canonical_state.py`
- `backend/negociacion/__init__.py`

### Archivos nuevos a crear

- `backend/negociacion/contexts/__init__.py`
- `backend/negociacion/contexts/resolver.py`
- `backend/negociacion/contexts/models.py`
- `backend/negociacion/contexts/defaults.py` o equivalente si se quiere separar constantes de baseline

---

## 4. Cambios exactos archivo por archivo

### `backend/negociacion/pipeline.py`

- **Responsabilidad hoy:** construir config vía `build_negotiation_pipeline_config()` sin identidad contextual explícita.
- **Cambio exacto:** hacer que `run_negotiation_agent()` pueda seguir llamando a `build_negotiation_pipeline_config()`, pero esa función pasará a resolver internamente un contexto baseline oficial.
- **Compatibilidad:** no se cambia la firma pública de `run_negotiation_agent()` en esta fase.

### `backend/negociacion/orchestration/flow_config.py`

- **Responsabilidad hoy:** define `NegotiationTurnConfig`, `NEGOTIATION_FLOW_DETAILS`, `PROMPTS_DIR` global y carga prompts/phase assets desde `config.prompts_dir`.
- **Cambio exacto:**
  - extraer la noción de `PROMPTS_DIR` hardcodeado a una resolución desde `contexts/resolver.py`;
  - mantener `build_negotiation_pipeline_config()` pero hacer que resuelva el baseline oficial y devuelva el mismo `prompts_dir` efectivo del baseline;
  - si hace falta, añadir campos compatibles como `context_id` / `context_version` a `NegotiationTurnConfig`, solo si no rompe consumidores actuales;
  - dejar `_load_phase_cards()` y `_load_phase_classifier_card()` intactos salvo que pasen a recibir rutas ya resueltas por el contexto oficial.
- **Compatibilidad:** el payload final de `NegotiationTurnConfig` para el baseline debe equivaler al actual.

### `backend/negociacion/state/canonical_state.py`

- **Responsabilidad hoy:** `_load_persona_defaults()` y `_load_negotiation_brief_defaults()` leen rutas globales hardcodeadas bajo `backend/negociacion/prompts/`.
- **Cambio exacto:**
  - extraer esa resolución a helpers nuevos como `resolve_context_persona_path()` y `resolve_context_negotiation_brief_path()` en `backend/negociacion/contexts/resolver.py`;
  - hacer que `_load_persona_defaults()` y `_load_negotiation_brief_defaults()` dejen de construir rutas por sí mismas y consuman el resolver del baseline oficial;
  - mantener `build_default_canonical_state()` igual en shape y payload final.
- **Compatibilidad:** si algo falla, fallback temporal a rutas legacy actuales durante esta fase.

### `backend/negociacion/__init__.py`

- **Responsabilidad hoy:** exponer `run_negotiation_agent`.
- **Cambio:** probablemente ninguno o solo compatibilidad import si se decide exponer resolver/context models.
- **Compatibilidad:** total.

### `backend/negociacion/contexts/models.py`

- **Responsabilidad nueva:** definir el shape mínimo del contexto resuelto (`context_id`, `context_version`, `prompts_dir`, paths de assets/evaluation, `public_slug`).

### `backend/negociacion/contexts/resolver.py`

- **Responsabilidad nueva:** resolver el contexto baseline oficial y devolver paths efectivos consumibles por runtime.
- **Funciones nuevas recomendadas:**
  - `resolve_negotiation_context(context_id: str | None = None)`
  - `resolve_default_negotiation_context()`
  - `resolve_context_prompts_dir(...)`
  - `resolve_context_persona_path(...)`
  - `resolve_context_negotiation_brief_path(...)`
  - `resolve_context_phase_cards_path(...)`
  - `resolve_context_phase_classifier_card_path(...)`
- **Compatibilidad:** permitir fallback al bundle legacy si el baseline oficial no está disponible o mientras coexisten dos fuentes de verdad.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  negociacion/
    contexts/
      __init__.py
      models.py
      resolver.py
      defaults.py   # opcional, si se separa configuración baseline
      baseline_current/
        ...
```

---

## 6. Qué NO se toca todavía

- `backend/interfaz_usuario/`
- `backend/interfaz_usuario_app/`
- `backend/sessions/state.py`
- `backend/evaluacion/`
- `backend/negociacion/optimizador/`
- `NegotiationPhase`
- shape de `CanonicalState`
- lógica de `finish_button_armed`

---

## 7. Cómo se garantiza equivalencia funcional

- el contexto resuelto por defecto debe apuntar al baseline oficial equivalente al bundle actual;
- `build_negotiation_pipeline_config()` sigue devolviendo mismos modelos/límites/flags;
- el `prompts_dir` efectivo del baseline contiene los mismos prompts que hoy;
- `build_default_canonical_state()` sigue produciendo el mismo payload de `persona` y `negotiation_brief`;
- no cambia el shape del estado;
- no cambia la API pública;
- no cambia evaluación visible;
- optimizer todavía no depende de esta resolución como identidad oficial.

---

## 8. Riesgos específicos de la fase

- runtime leyendo prompts desde baseline oficial pero canonical state leyendo JSON legacy, o viceversa;
- introducir campos en `NegotiationTurnConfig` que rompan validación o consumidores implícitos;
- dejar fallback demasiado opaco y acabar con dos fuentes de verdad indefinidas.

---

## 9. Validaciones y checks recomendados

- comparar `NegotiationTurnConfig` baseline antes/después;
- comparar hashes o contenido de prompts efectivos baseline antes/después;
- comparar payload de `build_default_canonical_state()` baseline antes/después;
- smoke check manual del caso actual para verificar respuesta equivalente en turnos básicos.

---

## 10. Condición de salida

El runtime completo del baseline se resuelve a través del contexto oficial, pero produce el mismo comportamiento observable que antes.

---

## 11. Rollback / compatibilidad

Mantener fallback explícito a las rutas legacy en `contexts/resolver.py` y/o en `canonical_state.py` durante esta fase permite volver temporalmente a la resolución anterior sin tocar el resto del motor.
