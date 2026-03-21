# Diagnóstico y reparación de la captura final embebida

## Alcance

Este ajuste se limita al repositorio del simulador, concretamente a:

- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/interfaz_usuario_app/index.html`

No se ha reescrito el contrato embebido principal (`ready`, `height`, `final_result_available`, `final_result`, envelope `ns`/`v`/`type`/`payload`).

## Diagnóstico exacto

### Qué ya funcionaba

El flujo principal ya estaba correcto:

1. el simulador embebido cargaba;
2. se emitían `ready` y `height`;
3. se emitían `final_result_available` y `final_result`;
4. Moodle aceptaba el payload y ejecutaba el ingest;
5. la UI de Moodle cambiaba a `saved`.

### Dónde se construía `final_result`

En `backend/interfaz_usuario_app/app.js`, mediante:

- `buildFinalResultPayload(report, extra)`
- `emitFinalResultLifecycle(report, { reason })`
- `fetchEvaluationReport(evaluationId)`

El pipeline previo era, en esencia:

`fetch report -> showFeedbackView('report') -> renderFinalReport(out.report) -> emitFinalResultLifecycle(out.report)`

### Dónde se generaba `snapshot_png_dataurl`

También en `buildFinalResultPayload(report, extra)`, a través de:

- `window.FeedbackReportView.captureReportPngDataUrl(report)`
- `blobToDataUrl(blob)` en `feedback_report_view.js`

### Qué root se capturaba antes

Antes no se capturaba el root visible ya renderizado del informe final. La captura se hacía sobre un root reconstruido offscreen con `buildDetachedReportRoot(report)` y posteriormente serializado dentro de un `SVG` con `foreignObject`.

### Momento de captura previo

Antes la estabilización era muy mínima:

- `document.fonts.ready`
- doble `requestAnimationFrame`

Luego se capturaba inmediatamente.

### Causa raíz más probable

La causa raíz no estaba en el contrato embebido, sino en la estrategia de rasterización final.

El problema residía en esta combinación:

1. captura sobre un clon offscreen en lugar del root visible ya asentado;
2. dependencia de `foreignObject` para convertir HTML a PNG;
3. validación inexistente del contenido realmente rasterizado;
4. fallback transparente de `1x1` disponible aunque el PNG real fuese visualmente incorrecto;
5. ausencia de logs diagnósticos suficientes para distinguir entre:
   - root todavía inestable,
   - dimensiones nulas,
   - rasterización vacía,
   - blob demasiado pequeño,
   - fallback real.

En la práctica, el flujo podía producir un PNG formalmente válido pero visualmente blanco/vacío.

## Reparación implementada

## Nuevo punto de verdad para captura

El punto de verdad queda definido así:

`render informe visible -> esperar estabilidad visual -> capturar -> validar PNG -> construir final_result -> enviar a Moodle`

Concretamente:

1. `fetchEvaluationReport()` obtiene el informe.
2. `showFeedbackView('report')` muestra la pantalla final.
3. `renderFinalReport(out.report)` renderiza el informe visible en `#feedbackReportRoot`.
4. `buildFinalResultPayload()` llama ahora a `captureReportPngDataUrl(report, { rootElement: captureRoot })` pasando explícitamente el root visible del informe final.
5. La captura espera estabilización real y valida el resultado antes de devolver `snapshot_png_dataurl`.

## Cómo se genera ahora el PNG

### Estrategia primaria

En `feedback_report_view.js` la captura primaria ahora:

1. usa el root visible cuando existe (`rootElement`), no solo un clon reconstruido;
2. espera `document.fonts.ready`;
3. espera tres `requestAnimationFrame` + una pausa corta de asentamiento;
4. comprueba varias lecturas consecutivas de tamaño para asegurar estabilidad del layout;
5. clona el root estable y elimina elementos efímeros como `.fb-turn-tooltip`;
6. rasteriza el clon mediante `SVG + foreignObject`;
7. valida el canvas muestreando píxeles para detectar rasterización blanca/vacía;
8. valida que el `Blob` no sea ridículamente pequeño.

### Estrategia secundaria de respaldo

Si la rasterización basada en `foreignObject` sale vacía o el blob es anómalo, se activa un renderer SVG de respaldo basado en datos del informe.

Ese respaldo:

- no devuelve un PNG vacío;
- compone un informe exportable con:
  - título,
  - actividad,
  - puntuación,
  - resumen final,
  - bloques principales,
  - recomendaciones.

Esto elimina el caso patológico de “PNG blanco pero formalmente válido”.

## Logs añadidos

Se añadieron logs explícitos para:

- métricas de estabilización del root;
- dimensiones finales de captura;
- resultado del muestreo del canvas;
- tamaño del blob PNG;
- activación del renderer SVG de respaldo;
- ACK de guardado recibido desde el padre.

## Fallback anterior y situación actual

### Antes

Existía `transparentFallbackPngDataUrl()` y podía terminar usándose cuando la serialización fallaba, dejando un PNG transparente como salida contractual.

### Ahora

Se mantiene el fallback transparente únicamente como última red de seguridad contractual dentro de `buildFinalResultPayload()`, pero el pipeline intenta primero:

1. captura real del root visible;
2. validación del raster;
3. renderer SVG de respaldo con contenido útil.

Es decir, el fallback transparente deja de ser la salida normal esperable.

## Handshake de guardado final

### Situación anterior

El simulador no recibía confirmación explícita desde Moodle tras el ingest exitoso. Por tanto, no había base sólida para mostrar una confirmación local “de verdad” después del guardado.

### Ajuste aplicado

Se añadió en `app.js` un listener de `postMessage` que acepta únicamente mensajes:

- desde `https://academia.gestionce.com`
- con `ns = 'gestionce.simulator'`
- con `v = 1`
- con `type = 'final_result_saved'`
- y `payload.status === 'ok'` o `payload.saved === true`

Solo en ese caso se muestra la notificación visual:

**Resultados guardados**

### Por qué así

Esto cierra el handshake sin romper la arquitectura actual:

- no altera `final_result`;
- no altera `final_result_available`;
- no cambia el envelope actual;
- añade solo un ACK complementario opcional desde el padre.

## Notificación visual en el simulador

Se añadió un toast visual integrado en `index.html`.

### Regla exacta

La notificación **solo** aparece cuando el simulador recibe una confirmación explícita y válida del padre indicando que el guardado final ha terminado correctamente.

No aparece:

- al renderizar el informe;
- al emitir `final_result_available`;
- al emitir `final_result`;
- si llega un mensaje no autorizado o con tipo distinto.

## Límites que siguen existiendo

1. Si Moodle todavía no emite el ACK `final_result_saved`, el simulador no puede demostrar por sí mismo que el guardado remoto terminó bien.
2. El renderer SVG de respaldo prioriza robustez y legibilidad; no replica al píxel toda la interacción DOM viva del informe.
3. La exportación sigue dependiendo del navegador para rasterización final del SVG a PNG.

## Pruebas manuales reproducibles

### Flujo embebido completo

1. Abrir Moodle con el simulador embebido.
2. Verificar en consola del padre que siguen entrando:
   - `ready`
   - `height`
   - `final_result_available`
   - `final_result`
3. Completar la evaluación hasta llegar al informe final.
4. Esperar a que el informe muestre nota, resultado y recomendaciones.
5. Confirmar en consola del iframe que aparecen logs `[feedback-capture]` con métricas y dimensiones útiles.
6. Confirmar en Moodle que el ingest devuelve `200` y la UI del padre cambia a `saved`.
7. Comprobar en “Mi cuaderno” que el PNG persistido ya no sale blanco.
8. Si el padre emite el ACK `final_result_saved`, verificar que aparece el toast **“Resultados guardados”** dentro del simulador.
9. Verificar que HTML, JSON y PNG siguen siendo descargables y coherentes.

### Prueba manual del ACK

En un entorno de pruebas embebido, emitir desde el padre algo equivalente a:

```js
iframe.contentWindow.postMessage({
  ns: 'gestionce.simulator',
  v: 1,
  type: 'final_result_saved',
  payload: { status: 'ok' }
}, 'https://academia.gestionce.com');
```

Resultado esperado:

- el simulador muestra el toast **“Resultados guardados”**;
- no se altera el resto del contrato embebido.
