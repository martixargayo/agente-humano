# Fase 08 — segundo contexto oficial

## 1. Propósito exacto de la fase

Validar el modelo completo incorporando un segundo contexto real dentro del mismo flow, sin tocar el motor estable.

Esta fase va la última porque solo tiene valor cuando la infraestructura de identidad contextual ya está cerrada.

---

## 2. Qué se cambia exactamente

Se crea un segundo contexto oficial completo y se verifica el flujo end-to-end:

- URL/entrada pública
- sesión
- runtime
- trazas
- evaluación
- optimizer

Todo sobre el nuevo contexto, sin cambiar el baseline.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/negociacion/contexts/...` (nueva carpeta de contexto)
- `backend/negociacion/contexts/public_mapping.py`
- `backend/interfaz_usuario_app/app.js` si hay selector/slug visible
- `backend/negociacion/optimizador/...` solo si hace falta registrar el nuevo contexto en listados
- `backend/evaluacion/domains/negotiation/...` si hay registro explícito de contextos disponibles

### Archivos nuevos a crear

- `backend/negociacion/contexts/<nuevo_context_id>/manifest.json`
- `backend/negociacion/contexts/<nuevo_context_id>/prompts/*`
- `backend/negociacion/contexts/<nuevo_context_id>/assets/*`
- `backend/negociacion/contexts/<nuevo_context_id>/evaluation/*`
- datasets/fixtures del nuevo contexto si se quieren validar eval/optimizer

---

## 4. Cambios exactos archivo por archivo

### `backend/negociacion/contexts/<nuevo_context_id>/...`

- **Responsabilidad nueva:** representar un segundo caso del mismo flow.
- **Cambio exacto:** crear bundle completo con prompts/assets/evaluation, sin tocar el motor.

### `backend/negociacion/contexts/public_mapping.py`

- **Cambio exacto:** registrar `public_slug -> nuevo_context_id`.

### `backend/interfaz_usuario_app/app.js`

- **Cambio exacto:** solo si hace falta exponer o leer el nuevo slug/contexto desde la URL. Evitar cambios de UX innecesarios.

### `backend/evaluacion/...`

- **Cambio exacto:** ningún cambio estructural si la fase 06 quedó bien; solo asegurar que el nuevo contexto resuelve sus assets propios.

### `backend/negociacion/optimizador/...`

- **Cambio exacto:** ningún cambio estructural si la fase 07 quedó bien; solo hacer visible el nuevo contexto como opción oficial.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  negociacion/
    contexts/
      baseline_current/
      <nuevo_context_id>/
        manifest.json
        prompts/
        assets/
        evaluation/
```

---

## 6. Qué NO se toca todavía

- motor estable de `backend/negociacion/`;
- shape del estado;
- enum de fases;
- lógica de finish button;
- pipeline de evaluación;
- mecanismo base del optimizer.

---

## 7. Cómo se garantiza equivalencia funcional

- el baseline sigue existiendo y sigue siendo el default compatible;
- no se tocan prompts/assets baseline;
- el motor sigue siendo el mismo;
- la nueva variación vive solo en la carpeta de contexto;
- cualquier cambio de comportamiento solo afecta al nuevo contexto, no al baseline actual.

---

## 8. Riesgos específicos de la fase

- el segundo contexto no cabe realmente en el mismo flow y obliga a tocar motor/estado;
- se crean prompts/assets nuevos pero se olvida su evaluación contextual;
- la URL pública y el optimizer resuelven distinto `context_id` para el nuevo caso.

---

## 9. Validaciones y checks recomendados

- smoke check completo del baseline para demostrar que no cambió;
- smoke check completo del nuevo contexto;
- comparación de trazas baseline vs nuevo contexto;
- evaluación del nuevo contexto con sus assets propios;
- optimizer ejecutando baseline y nuevo contexto de forma distinguible.

---

## 10. Condición de salida

El repo soporta al menos dos contextos oficiales del mismo flow sin necesidad de tocar el motor estable.

---

## 11. Rollback / compatibilidad

Si el nuevo contexto falla, puede retirarse su registro en `public_mapping.py` y su carpeta de contexto sin afectar el baseline ni el motor.
