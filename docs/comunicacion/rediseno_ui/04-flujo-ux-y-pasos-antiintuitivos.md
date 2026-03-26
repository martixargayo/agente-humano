# 04 · Flujo UX completo y pasos antiintuitivos (incluye post-grabación)

## 1) Objetivo del doc
Definir el journey futuro de `comunicacion` para que sea lineal, reversible y claro, eliminando fricciones actuales y encapsulando pasos técnicos detrás de CTAs comprensibles.

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `backend/interfaz_usuario_app/app.js` (referencia de simplicidad por estado)

## 3) Evidencia exacta encontrada en repo
- Flujo actual en `SCREEN_ORDER`:
  `intro -> permissions -> preview -> recording -> review -> uploading -> processing -> report`.
- CTAs actuales visibles:
  - `Empezar`, `Conceder permisos`, `Abrir preview`, `Grabar`, `Detener`, `Registrar grabación`, `Enviar a evaluar`.
- En review se muestran:
  - duración (`reviewDuration`),
  - MIME (`reviewMimeType`),
  - tamaño (`reviewBlobSize`),
  - referencia provisional (`reviewVideoRef`).
- `registerRecordingMetadata()` y `submitCommunicationAttempt()` son pasos internos separados hoy.

## 4) Diagnóstico del estado actual
- Doble/Triple confirmación antes de evaluar.
- Terminología técnica expuesta al usuario (metadata, referencia provisional).
- Ruptura del flujo mental: “si ya grabé, ¿por qué registrar y luego enviar?”.

## 5) Referencia visual/técnica exacta
- Negociación simplifica entrada con CTA contextual único.
- El patrón robusto es: menos botones, más estados inteligentes en backend/frontend.

## 6) Propuesta detallada de cómo debería quedar

### 6.1 Wizard UX objetivo
1. Setup permisos AV (`Empezar` cuando listo).
2. Paso AIDA editable (`Continuar`).
3. Grabación (`Grabar` / `Detener`).
4. Review simplificado + CTA único `Enviar y evaluar`.
5. Loading idéntica a negociación.
6. Feedback final.

### 6.2 Reglas de navegación
- `Atrás` permitido en 1→2→3→4.
- Una vez se pulsa `Enviar y evaluar`, no hay back a edición.
- Sin pantallas técnicas intermedias “uploading” visibles (pueden existir internamente).

### 6.3 Post-grabación solicitado
- Mantener visibles:
  - duración,
  - tamaño.
- Ocultar al usuario:
  - MIME,
  - referencias internas/provisionales.
- Eliminar botón `Registrar grabación`.
- CTA único: `Enviar y evaluar` (internamente ejecuta registro + submit).

## 7) Layout detallado
- Header de progreso: `Paso X de 6`.
- Cuerpo de cada paso centrado en una sola tarea.
- Footer de navegación consistente:
  - izquierda `Atrás`,
  - derecha CTA principal.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `registerRecordingMetadata()` | `backend/comunicacion_app/app.js` | Reutilizar interno | sigue siendo necesario técnicamente | encapsulado en CTA único |
| `submitCommunicationAttempt()` | `backend/comunicacion_app/app.js` | Reutilizar interno | dispara evaluación real | encadenado tras registro |
| `screenUploading` | `backend/comunicacion_app/index.html` | Descartar visible | paso técnico no UX | transición interna |
| `screenProcessing` | `backend/comunicacion_app/index.html` | Adaptar total | debe ser loading idéntica negociación | ver doc 05 |
| `reviewDuration` / `reviewBlobSize` | `backend/comunicacion_app/index.html` | Reutilizar | dato útil para usuario | review final simplificada |
| `reviewMimeType` / `reviewVideoRef` | `backend/comunicacion_app/index.html` | Descartar visual | dato técnico innecesario | oculto para debug interno |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/app.js` | `SCREEN_ORDER`, handlers review | funciones upload/submit | pasos visibles upload/processing técnicos | `sendAndEvaluate()` orquestador único | Medio |
| `backend/comunicacion_app/index.html` | sección review y navegación | nodos duración/tamaño | `Registrar grabación`, metadata técnica visible | CTA único y copy UX | Bajo |
| `backend/comunicacion_app/styles.css` | estilos de navegación | sistema botón base | estilos de bloques técnicos | patrón wizard consistente | Bajo |

## 10) Riesgos o puntos delicados
- Encapsular registro+submit debe manejar bien errores sin reintroducir complejidad visible.
- Debe conservarse trazabilidad técnica en logs aunque no se muestre en UI.
- Evitar estados imposibles al usar botón atrás después de modificar blobs/attempt.

## 11) Criterio de aceptación visual/UX
- El usuario percibe un flujo corto, lineal y con lógica obvia.
- Después de grabar sólo existe una acción principal: `Enviar y evaluar`.
- No aparecen términos técnicos internos en la experiencia normal.
