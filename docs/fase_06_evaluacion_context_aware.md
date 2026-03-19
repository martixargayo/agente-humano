# Fase 06 — evaluación context-aware

## 1. Propósito exacto de la fase

Hacer que la evaluación use los prompts/rúbrica del contexto correcto, sin rediseñar el pipeline de evaluación ni cambiar el informe visible del baseline.

Va después de trazas y sesión porque la evaluación necesita identidad contextual persistida para ser fiable.

---

## 2. Qué se cambia exactamente

Se vuelve contextual la resolución de assets evaluativos y se propaga identidad contextual al bundle/job/provenance.

### Objetivo técnico

Que la evaluación pueda responder:

- qué contexto está evaluando;
- qué prompts evaluativos está usando;
- qué rúbrica está usando;
- y que para el baseline esos assets sean exactamente los actuales.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/provenance.py` si hace falta extender hashing/provenance
- `backend/evaluacion/engine/runners/core_runner.py`
- `backend/evaluacion/engine/runners/trajectory_runner.py`
- `backend/evaluacion/engine/runners/common.py`
- `backend/evaluacion/api/models.py`
- `backend/evaluacion/domains/negotiation/rubric_loader.py`
- `backend/evaluacion/contracts/models.py` si se decide ampliar `DomainContext` o bundle

### Archivos nuevos a crear

- `backend/evaluacion/domains/negotiation/context_resolver.py`
- `backend/evaluacion/domains/negotiation/assets_loader.py`

---

## 4. Cambios exactos archivo por archivo

### `backend/evaluacion/domains/negotiation/extractor.py`

- **Responsabilidad hoy:** construir `FeedbackInputBundleV1` desde sesión con `domain="negociacion"`, fase final y finish button.
- **Cambio exacto:**
  - ampliar el bundle o `DomainContext` para incluir `context_id/context_version` del baseline;
  - seguir extrayendo el resto del bundle exactamente igual.
- **Compatibilidad:** si falta contexto, fallback al baseline.

### `backend/evaluacion/engine/service.py`

- **Responsabilidad hoy:** crear job y ejecutar pipeline sin identidad contextual explícita.
- **Cambio exacto:**
  - persistir en job/artifacts/provenance los metadatos contextuales;
  - no cambiar la secuencia del pipeline.
- **Compatibilidad:** total para baseline.

### `backend/evaluacion/domains/negotiation/rubric_loader.py`

- **Responsabilidad hoy:** cargar una única rúbrica global desde ruta fija.
- **Cambio exacto:**
  - mover la resolución de la rúbrica a un loader contextual;
  - mantener la rúbrica baseline actual como la del contexto baseline.
- **Compatibilidad:** el baseline sigue usando la misma rúbrica efectiva.

### `backend/evaluacion/engine/runners/core_runner.py` y `trajectory_runner.py`

- **Responsabilidad hoy:** cargar prompts desde rutas fijas globales.
- **Cambio exacto:**
  - reemplazar ruta fija por resolver contextual según `context_id` del bundle;
  - mantener mismos prompts efectivos en baseline.
- **Compatibilidad:** si no hay contexto explícito, usar baseline.

### `backend/evaluacion/engine/runners/common.py`

- **Cambio exacto:** probablemente ninguno sustantivo; solo helpers de lectura si se centraliza resolución.

### `backend/evaluacion/api/models.py`

- **Cambio exacto:** opcionalmente exponer `context_id` en respuestas de status/report si se quiere visibilidad API, manteniéndolo compatible.

### `backend/evaluacion/domains/negotiation/context_resolver.py` / `assets_loader.py`

- **Responsabilidad nueva:** resolver prompts evaluativos y rúbrica del contexto.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  evaluacion/
    domains/
      negotiation/
        context_resolver.py
        assets_loader.py
```

---

## 6. Qué NO se toca todavía

- formato visible del informe;
- scoring del baseline;
- frontend del feedback;
- segundo contexto oficial si aún no está listo;
- lógica negociadora del runtime.

---

## 7. Cómo se garantiza equivalencia funcional

- el baseline usa exactamente los mismos prompts/rúbrica que hoy;
- el pipeline `bundle -> core -> trajectory -> reconciliation -> report` sigue igual;
- no cambia el shape visible del informe para el baseline;
- no cambia la API actual salvo campos opcionales;
- no cambia el runtime de negociación.

---

## 8. Riesgos específicos de la fase

- evaluación leyendo contexto baseline desde sesión vieja sin `context_id`;
- prompts evaluativos contextuales resueltos bien pero rúbrica todavía global, o viceversa;
- bundle de evaluación con contexto distinto al de la traza o sesión.

---

## 9. Validaciones y checks recomendados

- comparar baseline report antes/después con mismos prompts/rúbrica efectivos;
- comprobar que jobs/provenance guardan `context_id`;
- testear fallback baseline para sesiones antiguas.

---

## 10. Condición de salida

La evaluación sabe qué contexto está evaluando y usa sus assets correctos, manteniendo el mismo resultado visible del baseline.

---

## 11. Rollback / compatibilidad

Mantener fallback al loader global baseline mientras se estabiliza la resolución contextual.
