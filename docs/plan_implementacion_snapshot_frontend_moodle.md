# Plan de implementación: migración del snapshot final a un pipeline frontend-only robusto

## 1. Resumen ejecutivo

Este plan propone sustituir la estrategia actual de captura visual del informe final por un pipeline frontend-only más robusto, manteniendo intacto el contrato actual con Moodle. El problema a resolver no está en la persistencia ni en el embebido, sino en la generación del `snapshot_png_dataurl`: hoy la miniatura puede salir blanca o transparente porque la ruta principal de captura serializa manualmente el DOM del informe a un SVG con `<foreignObject>`, lo carga mediante `Blob URL` en un `Image`, y falla precisamente en `img.onerror` antes de poder rasterizar al canvas. Cuando eso ocurre, el sistema cae en un fallback PNG transparente de 1×1, que preserva el contrato técnico pero degrada el resultado funcional. La propuesta es mantener la captura en el frontend del simulador, capturando el root visible real del informe final, añadir un preflight de estabilidad visual, sustituir el serializer manual actual por un motor principal de captura DOM más robusto y complementarlo con un fallback real de familia distinta. Esta estrategia minimiza el impacto porque no requiere tocar Moodle, no obliga a cambiar `final_result.payload`, no altera el render del informe visible y no afecta al flujo de `ready`, `height`, `final_result_available` ni `final_result`; la intervención queda concentrada en la capa de snapshot del simulador y, como mucho, en la política de error asociada al campo `snapshot_png_dataurl`.

## 2. Estado actual del sistema

### 2.1 Render del informe final

El flujo actual de evaluación termina en `fetchEvaluationReport(evaluationId)` dentro de `backend/interfaz_usuario_app/app.js`. Esa función recupera el informe desde `/feedback/evaluations/:id/report`, cambia la UI a la vista `report`, llama a `renderFinalReport(out.report)` y, a continuación, emite el ciclo embebido final con `emitFinalResultLifecycle(out.report, { reason: 'report-fetched' })`. `renderFinalReport(report)` usa `#feedbackReportRoot` como contenedor visible del informe y delega el render en `window.FeedbackReportView.renderReport(root, report)`. El root visible real del informe es por tanto `#feedbackReportRoot`, definido dentro de `#feedbackReportScreen` en `backend/interfaz_usuario_app/index.html`.

### 2.2 Root capturado hoy

La composición del payload final ocurre en `buildFinalResultPayload(report, extra)`, también en `backend/interfaz_usuario_app/app.js`. Esa función obtiene `const captureRoot = $('feedbackReportRoot')` y llama a `window.FeedbackReportView.captureReportPngDataUrl(report, { rootElement: captureRoot })`. Eso significa que la intención actual ya es capturar el root visible real del informe, no una reconstrucción independiente. Solo si ese root no existe o no está conectado al DOM, `captureReportAsPng(report, options)` en `backend/interfaz_usuario_app/feedback_report_view.js` construye un root alternativo mediante `buildDetachedReportRoot(report)` y captura sobre él.

### 2.3 Generación actual del snapshot

La lógica principal de snapshot está encapsulada en `captureReportAsPng(report, options)` dentro de `backend/interfaz_usuario_app/feedback_report_view.js`. Su pipeline actual es:

1. resolver `liveRoot` desde `options.rootElement`;
2. si no hay root conectado, construir `sandboxRoot` con `buildDetachedReportRoot(report)`;
3. esperar estabilización básica con `waitForStableReportCapture(captureRoot, { requireVisible: captureRoot === liveRoot })`;
4. medir dimensiones del root con `getCaptureRootMetrics` y calcular `width`/`height`;
5. clonar el root con `cloneNode(true)`;
6. retirar tooltips (`.fb-turn-tooltip`) del clon;
7. serializar el clon a un string SVG que contiene un `<foreignObject>` y una etiqueta `<style>` con `getFeedbackReportStyles()`;
8. construir `Blob([svgMarkup], { type: 'image/svg+xml;charset=utf-8' })`;
9. crear `svgUrl` mediante `URL.createObjectURL(svgBlob)`;
10. cargarlo en un `Image`;
11. al llegar `onload`, dibujarlo sobre un `canvas` blanco con `drawImage`;
12. convertir el canvas a PNG con `canvas.toBlob`;
13. convertir el `Blob` resultante a Data URL mediante `blobToDataUrl`.

### 2.4 Punto exacto de fallo

El error dominante actual se produce en la carga del SVG generado manualmente:

- `img.onerror = () => reject(new Error('No se pudo rasterizar el informe a PNG.'));`
- `img.src = svgUrl;`

Es decir, la avería no está en `canvas.toBlob`, ni en `postMessage`, ni en Moodle, sino en la transición SVG serializado -> `Image` dentro del frontend del simulador.

### 2.5 Fallback transparente actual

`buildFinalResultPayload(report, extra)` inicializa `snapshotPngDataUrl` con `transparentFallbackPngDataUrl()`, que devuelve un PNG transparente de 1×1. Si `captureReportPngDataUrl(...)` lanza una excepción, el `catch` registra el warning embebido y deja ese fallback transparente en `snapshot_png_dataurl`.

Es importante distinguir dos niveles de fallback actuales:

- **Fallback interno de `feedback_report_view.js`**: si la rasterización basada en `foreignObject` sí llega a canvas pero la muestra del bitmap sale vacía o el blob PNG es demasiado pequeño, la función intenta `renderReportFromDataAsPng(report, { width })`, un renderer SVG simplificado basado en datos.
- **Fallback externo de `app.js`**: si la ruta principal falla antes de llegar a canvas —por ejemplo, en `img.onerror`— la excepción sube a `buildFinalResultPayload` y el sistema termina usando el PNG transparente de 1×1.

Por eso el fallback “visual” actual no cubre el caso dominante que genera la miniatura blanca/transparente.

### 2.6 Inserción en el payload y puntos que deben preservarse

`buildFinalResultPayload` compone el payload final con `report`, `report_html`, `summary_html`, `report_json`, `payloadjson` y `snapshot_png_dataurl`. Después añade `payload_hash` y `emitFinalResultLifecycle` emite primero `final_result_available` y luego `final_result` a través de `emitEmbedMessage`, que envía el envelope con `window.parent.postMessage(envelope, PARENT_EMBED_ORIGIN)`.

Estos puntos del flujo están funcionando correctamente y deben preservarse:

- render del informe visible con `FeedbackReportView.renderReport`;
- root visible `#feedbackReportRoot` como referencia funcional del informe final;
- composición del payload en `buildFinalResultPayload`;
- emisión embebida de `final_result_available`;
- emisión embebida de `final_result`;
- envío mediante `postMessage`;
- persistencia y consumo posterior en Moodle.

## 3. Objetivo técnico de la migración

La migración debe dejar el sistema en un estado donde la captura del informe final siga realizándose en frontend, pero sin depender del serializer manual actual como ruta principal. El estado objetivo debe cumplir simultáneamente estas condiciones:

1. capturar por defecto el root visible real del informe final (`#feedbackReportRoot`);
2. esperar explícitamente a que fuentes, recursos visuales y layout estén estables antes de capturar;
3. usar un motor principal de captura DOM más robusto que el pipeline manual `cloneNode -> SVG + foreignObject -> Blob URL -> Image`;
4. usar un fallback alternativo de familia distinta para no repetir el mismo modo de fallo;
5. seguir devolviendo un PNG en Data URL apto para `snapshot_png_dataurl`;
6. mantener sin cambios el contrato del payload enviado a Moodle;
7. eliminar como comportamiento normal el fallback transparente silencioso que hoy oculta la avería real.

Se considerará que la migración ha tenido éxito cuando el simulador siga enviando el mismo `final_result.payload` que hoy espera Moodle, pero la generación de `snapshot_png_dataurl` deje de producir miniaturas blancas/transparente en los casos normales y el sistema pueda distinguir de forma observable entre captura exitosa, fallback exitoso y fallo real.

## 4. Arquitectura propuesta

### 4.1 Root de captura

El nodo objetivo de captura debe ser el root visible real del informe final: `#feedbackReportRoot`. La razón es funcional y técnica:

- es el contenedor sobre el que `renderFinalReport(report)` ya pinta el informe definitivo;
- es el nodo que ya utiliza `buildFinalResultPayload` como `rootElement` para la captura actual;
- evita divergencias entre el contenido que ve la persona usuaria y una reconstrucción “parecida” montada aparte.

El root reconstruido mediante `buildDetachedReportRoot(report)` puede mantenerse solo como ruta de contingencia secundaria, por ejemplo para exportación fuera de pantalla o como último recurso si el root visible no existe. No debería ser la ruta principal de snapshot porque aumenta el riesgo de divergencia visual respecto al informe realmente mostrado.

### 4.2 Preflight

Antes de invocar cualquier motor de captura, el pipeline debería ejecutar una fase formal de preflight sobre el root visible. Esa fase debería incluir, como mínimo:

1. **Espera de fuentes**: `document.fonts.ready` ya existe en `waitForStableReportCapture` y debe preservarse como requisito de entrada.
2. **Espera de imágenes si existen**: el informe actual no depende de `<img>`, pero el preflight debería quedar preparado para detectar imágenes futuras dentro de `reportRoot` y esperar a su `complete`/`decode()`.
3. **Estabilización de layout**: se puede reutilizar la lógica actual de `getCaptureRootMetrics`, `metricsAreStable` y `waitForStableReportCapture`, ampliándola si es necesario con uno o dos frames adicionales una vez renderizado el informe.
4. **Frames de espera**: debe mantenerse una pequeña ventana de estabilización tras el render final para absorber repaints diferidos y resolver métricas definitivas.
5. **Congelación de animaciones y transiciones si aplica**: el informe actual no parece depender de animaciones complejas, pero el plan debe prever que el clon de captura desactive transiciones, cursores, tooltips o estados efímeros si en el futuro se introducen.
6. **Validaciones previas**:
   - root presente y conectado;
   - dimensiones positivas y razonables;
   - ancho/alto finales de captura registrados;
   - fondo opaco explícito si el motor lo necesita;
   - eliminación o exclusión de nodos efímeros que no deban aparecer en la miniatura.

### 4.3 Motor principal

El motor principal recomendado para este repositorio es un capturador DOM de propósito específico de la familia `html-to-image` o equivalente funcional. La recomendación no es una preferencia abstracta, sino un encaje concreto con el repo:

- el informe final ya existe como DOM visible, encapsulado en `FeedbackReportView.renderReport`;
- el CSS del informe está concentrado en `feedback_report_view.js` y no repartido por una gran librería de UI externa;
- el root visible tiene estructura relativamente controlada (tarjetas, texto, SVG inline, gráfico SVG propio);
- el principal problema actual nace precisamente en el serializer manual con `foreignObject`, no en la idea de capturar desde frontend.

Ventajas del motor principal propuesto frente al pipeline manual actual:

- reduce la dependencia de la serialización artesanal del DOM;
- elimina la necesidad de mantener a mano la ruta `SVG + foreignObject + Image` como solución primaria;
- favorece una captura basada en el nodo real visible;
- simplifica el reemplazo sin tocar el contrato de `captureReportPngDataUrl`.

Limitaciones a vigilar con el motor principal:

- compatibilidad efectiva con el navegador embebido real;
- tratamiento de fuentes externas (en este caso, la fuente `Inter` importada desde Google Fonts en `ensureStyles()`);
- fidelidad de SVG inline y del gráfico del informe;
- coste de memoria si el informe crece mucho en altura o si se fuerza una escala alta.

### 4.4 Fallback real

El fallback recomendado es un motor de familia distinta, del estilo `html2canvas` sin `foreignObject`. Debe ser de familia distinta porque el objetivo del fallback no es repetir el mismo pipeline con pequeños cambios, sino romper la correlación de fallos. Si el motor principal falla por una incompatibilidad de serialización, de fuentes o de recursos en la ruta DOM-capture primaria, el fallback debe apoyarse en otro enfoque de render para maximizar la probabilidad de producir un PNG utilizable.

El fallback debería activarse ante fallos como:

- error explícito del motor principal;
- imagen/canvas generado pero vacío;
- blob PNG inválido o demasiado pequeño;
- validaciones post-captura que indiquen ausencia de contenido visible.

La expectativa de fidelidad del fallback no debe ser “pixel perfect”; debe ser suficiente para que la miniatura sea legible, estructuralmente correcta y claramente no blanca/transparente. Su función es preservar la utilidad de la vista previa cuando el principal no puede hacerlo.

### 4.5 Política de error

No debe mantenerse el fallback transparente silencioso como comportamiento normal porque:

- oculta el fallo real de captura;
- genera una miniatura engañosa que parece “válida” desde el punto de vista técnico;
- contamina Moodle con una salida visualmente inútil aunque el resto del payload sea correcto.

Si principal y fallback fallan, el sistema debería adoptar una política explícita. Las opciones conceptuales son:

1. **Devolver `null` en `snapshot_png_dataurl`** y acompañarlo de un metadato de error adicional si el contrato lo permite.
2. **Generar un placeholder explícito** con fondo blanco y texto del tipo “Vista previa no disponible”, manteniendo `snapshot_png_dataurl` siempre informado.
3. **Mantener temporalmente el fallback transparente**, pero solo durante transición y con observabilidad fuerte.

La recomendación para este repositorio es una transición en dos etapas:

- durante la migración: mantener compatibilidad funcional pero registrar exhaustivamente cuándo se usa la ruta de error;
- una vez estabilizado el pipeline nuevo: sustituir el fallback transparente silencioso por una salida explícita y observable.

## 5. Mapa exacto de impacto en el repositorio

### 5.1 Archivos candidatos a tocar si se implementa el plan

1. **`backend/interfaz_usuario_app/feedback_report_view.js`**
   - archivo principal de la migración;
   - concentra render del informe, helpers de estabilidad y la captura actual.
2. **`backend/interfaz_usuario_app/app.js`**
   - archivo de integración del snapshot con el payload final;
   - probable punto para ajustar política de error y observabilidad asociada a `snapshot_png_dataurl`.
3. **`backend/interfaz_usuario_app/index.html`**
   - no parece requerir cambios funcionales significativos, pero define el root visible `#feedbackReportRoot` y la disposición de la vista `report`.
4. **Documentación adicional en `docs/`**
   - opcionalmente para seguimiento, checklist o rollout, si el equipo decide acompañar la implementación con documentos operativos.

### 5.2 Funciones candidatas a sustituirse

En `backend/interfaz_usuario_app/feedback_report_view.js`:

- `captureReportAsPng(report, options)` — candidata principal a reimplementación interna del pipeline.
- `renderReportFromDataAsPng(report, options)` — candidata a mantenerse solo como fallback remoto/diagnóstico o a ser relegada si el nuevo fallback la sustituye completamente.

### 5.3 Funciones candidatas a envolverse

En `backend/interfaz_usuario_app/feedback_report_view.js`:

- `captureReportPngDataUrl(report, options)` — buen punto de envoltura para mantener la API pública actual mientras cambia la implementación inferior.

En `backend/interfaz_usuario_app/app.js`:

- `buildFinalResultPayload(report, extra)` — no para cambiar contrato, sino para envolver con mejor logging y una política de error más expresiva.

### 5.4 Funciones que conviene mantener y reutilizar

En `backend/interfaz_usuario_app/feedback_report_view.js`:

- `renderReport(container, report, options)` — debe mantenerse como fuente del DOM visible real.
- `buildDetachedReportRoot(report)` — útil como contingencia secundaria.
- `getCaptureRootMetrics(root)` — reutilizable para medición.
- `metricsAreStable(current, previous)` — reutilizable para estabilidad.
- `waitForStableReportCapture(root, options)` — reutilizable y ampliable como parte del preflight.
- `blobToDataUrl(blob)` — reutilizable para la serialización final.

En `backend/interfaz_usuario_app/app.js`:

- `buildFinalResultPayload(report, extra)` — debe seguir siendo el punto de composición del payload.
- `emitFinalResultLifecycle(report, options)` — debe preservarse.
- `emitEmbedMessage(type, payload, options)` — debe preservarse sin cambios funcionales.

### 5.5 Mejor punto para cada responsabilidad futura

- **Preflight**: dentro de `feedback_report_view.js`, inmediatamente antes del motor de captura, reutilizando y ampliando `waitForStableReportCapture`.
- **Selección de motor**: dentro de `captureReportAsPng`, para que la decisión quede encapsulada en la capa de snapshot y `app.js` no necesite saber qué motor produjo el PNG.
- **Fallback**: dentro de `captureReportAsPng`, a continuación del principal y con registro explícito del motivo de activación.
- **Logging**: principalmente dentro de `captureReportAsPng`, con refuerzo puntual en `buildFinalResultPayload` para registrar la decisión final sobre `snapshot_png_dataurl`.
- **Serialización final a Data URL**: `captureReportPngDataUrl`, preservando su papel actual como wrapper de `Blob -> Data URL`.

### 5.6 Flujo embebido que no debería tocarse

No deberían alterarse, salvo para observabilidad no intrusiva:

- `buildEmbedEnvelope`;
- `emitEmbedMessage`;
- el contenido contractual de `final_result_available`;
- el contenido contractual de `final_result`;
- el uso de `window.parent.postMessage`;
- la correlación ACK de `final_result_saved`.

## 6. Plan de implementación por fases

### Fase 0. Preparación y observabilidad

Objetivo: introducir trazabilidad suficiente para medir la mejora y diagnosticar fallos sin depender de la miniatura final como única señal.

Elementos a registrar:

- identificador del root capturado (`live-root` vs `sandbox-root`);
- dimensiones CSS y bitmap finales;
- tiempo de preflight;
- motor seleccionado (`principal` / `fallback` / `legacy` si se mantiene temporalmente);
- error de preflight;
- error del motor principal;
- error del fallback;
- tamaño del blob PNG final;
- validación de contenido visible del bitmap resultante.

Recomendación operativa:

- diferenciar claramente en logs errores de `preflight`, `primary-engine`, `fallback-engine` y `payload-serialization`;
- si se mantiene durante transición el pipeline viejo, registrar de forma inequívoca qué motor produjo el snapshot que terminó en `snapshot_png_dataurl`.

### Fase 1. Introducción del nuevo pipeline

Objetivo: conectar un nuevo motor principal sin romper el contrato actual con `app.js` ni con Moodle.

Plan:

1. mantener `captureReportPngDataUrl(report, options)` como superficie pública;
2. introducir en `captureReportAsPng(report, options)` una nueva secuencia:
   - resolver root visible real;
   - ejecutar preflight;
   - capturar con motor principal nuevo;
   - validar resultado;
   - devolver `Blob` PNG;
3. mantener `buildFinalResultPayload` sin cambio contractual, de modo que siga esperando exactamente una Data URL.

Durante esta fase conviene preservar compatibilidad con el flujo actual, incluso si temporalmente se mantiene una ruta heredada utilizable solo para diagnóstico o rollback.

### Fase 2. Introducción del fallback alternativo

Objetivo: cubrir fallos del principal con un segundo motor no dependiente de la misma cadena de fallos.

Reglas de activación recomendadas:

- excepción del motor principal;
- rasterización vacía o casi vacía;
- blob nulo o PNG sospechosamente pequeño;
- resultado que no supere validaciones mínimas de visibilidad.

Comportamiento esperado del fallback:

- devolver también un `Blob` PNG apto para `blobToDataUrl`;
- registrar explícitamente que el snapshot fue producido por el fallback;
- adjuntar, al menos en logs, el motivo de activación.

### Fase 3. Cambio de política de error

Objetivo: retirar el uso silencioso del PNG transparente de 1×1 como salida por defecto.

Transición sugerida:

1. en una primera etapa, mantener compatibilidad pero registrar todos los casos que siguen llegando al fallback transparente;
2. cuando el nuevo pipeline sea estable, cambiar la política para que un fallo doble (principal + fallback) no genere una miniatura silenciosamente vacía;
3. adoptar una salida explícita aceptable para la transición, preferiblemente:
   - `snapshot_png_dataurl` nulo si el contrato lo soporta sin romper consumidores; o,
   - placeholder explícito si el contrato exige siempre un PNG.

Criterio rector: evitar que Moodle almacene como miniatura “válida” algo que solo es una transparencia muda.

### Fase 4. Endurecimiento y limpieza

Una vez verificado que la tasa de éxito del nuevo pipeline es estable, convendría:

- deprecar la ruta basada en serializer manual como solución primaria;
- decidir si `renderReportFromDataAsPng` se conserva solo como herramienta diagnóstica o se retira del camino principal;
- retirar logs temporales excesivamente verbosos y dejar solo telemetría útil;
- consolidar la política final de error y documentarla;
- eliminar referencias heredadas al fallback transparente como comportamiento “normal”.

## 7. Estrategia de validación y pruebas

### 7.1 Validación funcional

La migración debe demostrar que no rompe el sistema ya sano. Debe verificarse que:

- el informe visible renderizado por `FeedbackReportView.renderReport` sigue viéndose igual;
- `snapshot_png_dataurl` sigue existiendo cuando la captura es exitosa;
- `final_result_available` mantiene su estructura actual;
- `final_result` mantiene su estructura actual;
- Moodle sigue recibiendo el mismo contrato funcional por `postMessage`.

La validación funcional debe centrarse en comprobar que cambia la forma de producir el PNG, no el shape del payload ni el comportamiento embebido.

### 7.2 Validación visual

La validación visual debe confirmar que:

- la miniatura ya no sale blanca/transparente en los casos normales;
- el snapshot resultante es legible;
- la estructura general del informe se conserva;
- el encabezado, score, tarjetas, recomendaciones y gráfica mantienen una representación razonable;
- la tipografía y los SVG inline quedan dentro de un umbral aceptable aunque no sean exactamente idénticos píxel a píxel.

### 7.3 Casos de prueba a cubrir

Se recomienda cubrir explícitamente, como mínimo, estos escenarios:

1. informe corto con pocas recomendaciones;
2. informe largo con varias recomendaciones y mayor altura;
3. informe sin recomendaciones;
4. informe con trayectoria de conversación y gráfico SVG presente;
5. informe con distinta altura de root y necesidad de scroll;
6. captura con root visible real conectado al DOM;
7. captura con fallback a root reconstruido, si esa ruta se mantiene;
8. condiciones de red lenta o bloqueo parcial de fuentes, para medir degradación tipográfica;
9. casos donde el motor principal falle y deba activarse el fallback;
10. casos donde el fallback también falle, para validar la política de error elegida.

### 7.4 Validación de robustez

La robustez no debe medirse solo por “se generó una Data URL”, sino por señales adicionales:

- detección de snapshots vacíos mediante muestreo básico del canvas o heurística equivalente;
- detección de PNG inválido o blob de tamaño anómalo;
- comparación de tasa de éxito del motor principal frente a la tasa actual;
- reducción efectiva de casos que terminan en miniatura blanca/transparente;
- capacidad de distinguir en observabilidad qué motor produjo el resultado final.

Indicadores prácticos de mejora real:

- disminución drástica de `img.onerror` o de errores equivalentes de captura;
- reducción de blobs PNG de tamaño irrealmente pequeño;
- desaparición de entradas nuevas en Moodle con miniatura blanca/transparente en condiciones normales.

## 8. Riesgos técnicos y mitigaciones

### 8.1 Compatibilidad del navegador embebido real

**Riesgo**: el repositorio no identifica de forma concluyente el navegador embebido real que ejecuta la captura en producción.

**Mitigación**:

- validar la solución en el runtime embebido real, no solo en navegador de escritorio local;
- instrumentar motor usado, éxito/fallo y tamaño final del PNG;
- mantener un rollback temporal si el entorno embebido muestra incompatibilidades inesperadas.

### 8.2 Google Fonts o fuentes externas

**Riesgo**: `ensureStyles()` importa `Inter` desde Google Fonts, lo que puede introducir dependencia de carga externa o diferencias visuales.

**Mitigación**:

- mantener `document.fonts.ready` en el preflight;
- aceptar degradación controlada a fuentes del sistema si la captura no puede garantizar la fuente remota;
- observar específicamente diferencias visuales en tipografía durante la validación.

### 8.3 SVG inline

**Riesgo**: el informe incluye estrellas SVG inline y un gráfico SVG generado dinámicamente.

**Mitigación**:

- validar explícitamente estos elementos con el motor principal y el fallback;
- excluir listeners o estados efímeros del árbol capturado si fuese necesario;
- tratar la fidelidad del fallback como “suficiente para miniatura”, no necesariamente idéntica a la vista interactiva.

### 8.4 Pixel ratio y memoria

**Riesgo**: informes altos o escalas elevadas pueden disparar el consumo de memoria del canvas o del motor de captura.

**Mitigación**:

- registrar ancho/alto finales y tamaño del blob;
- fijar una escala/pixel ratio máximos razonables;
- probar informes de gran altura;
- evitar configuraciones que generen bitmaps innecesariamente gigantes para una miniatura.

### 8.5 Diferencias entre root visible y root reconstruido

**Riesgo**: si se captura sobre `buildDetachedReportRoot(report)` pueden aparecer divergencias visuales respecto al root real mostrado.

**Mitigación**:

- usar siempre `#feedbackReportRoot` como ruta principal;
- dejar el root reconstruido solo como contingencia técnica;
- registrar qué tipo de root se usó en cada captura.

### 8.6 Dependencias de CSS global

**Riesgo**: el informe depende de estilos inyectados por `ensureStyles()` y puede verse afectado por contexto global si el motor no captura bien la cascada.

**Mitigación**:

- capturar el root visible real ya pintado;
- mantener el CSS del informe lo más autocontenido posible;
- validar que el motor principal respete adecuadamente ese aislamiento.

### 8.7 Timing de render

**Riesgo**: iniciar la captura antes de que el informe esté estabilizado puede seguir generando artefactos vacíos o incompletos.

**Mitigación**:

- conservar y reforzar la fase de preflight;
- esperar fuentes, recursos y varios frames estables;
- registrar tiempos y métricas de estabilización.

### 8.8 Divergencia entre motor principal y fallback

**Riesgo**: el fallback puede producir una miniatura visualmente distinta del principal.

**Mitigación**:

- definir desde el principio que la prioridad del fallback es legibilidad y robustez, no igualdad perfecta;
- validar ambos motores con el mismo conjunto de informes de referencia;
- registrar con claridad qué motor produjo cada resultado.

### 8.9 Tamaño del PNG final

**Riesgo**: un PNG excesivamente grande impacta payload y almacenamiento; uno demasiado pequeño puede ser síntoma de captura inválida.

**Mitigación**:

- registrar tamaño del blob;
- fijar umbrales de alerta para blobs sospechosamente pequeños;
- revisar resolución objetivo para equilibrar legibilidad y peso.

### 8.10 Mantenimiento futuro

**Riesgo**: seguir manteniendo varias rutas de captura aumenta complejidad si no se limpian tras la migración.

**Mitigación**:

- definir desde el inicio una fase de retirada de la ruta antigua;
- documentar el pipeline definitivo y sus criterios de error;
- minimizar código heredado una vez consolidada la solución.

## 9. Estrategia de rollout

Se recomienda un rollout progresivo y observable.

### 9.1 Feature flag

Sí conviene un feature flag o mecanismo equivalente de activación controlada, aunque sea de uso interno. Permite:

- comparar temporalmente el pipeline nuevo con el comportamiento actual;
- limitar el alcance inicial de la migración;
- revertir rápidamente si el navegador embebido real presenta problemas no detectados.

### 9.2 Transición progresiva

La transición ideal sería:

1. introducir observabilidad y nuevo principal con activación controlada;
2. añadir fallback alternativo;
3. comparar tasas de éxito, calidad visual y tamaño del PNG;
4. mover el nuevo pipeline a comportamiento por defecto;
5. retirar la ruta manual antigua cuando el éxito sea consistente.

### 9.3 Mantenimiento temporal del pipeline anterior

Conviene mantener temporalmente la ruta anterior solo como referencia de compatibilidad o rollback, no como solución de largo plazo. Mantenerla indefinidamente como sistema principal no es recomendable porque el problema actual nace de esa arquitectura.

### 9.4 Criterios para declarar éxito

Se debería declarar éxito cuando se cumplan simultáneamente estos criterios:

- el contrato de `final_result.payload` no cambia;
- Moodle sigue persistiendo entradas sin incidencias nuevas;
- las miniaturas blancas/transparente desaparecen en condiciones normales;
- el fallback alternativo cubre fallos del principal con resultados legibles;
- la tasa de uso del fallback transparente se reduce a cero o a casos de error explícitamente conocidos;
- el equipo puede identificar en logs qué motor produjo cada snapshot relevante.

### 9.5 Retirada de la ruta antigua

La ruta antigua debería retirarse cuando:

- el nuevo pipeline haya superado el periodo de validación acordado;
- el navegador embebido real haya sido validado;
- el fallback alternativo haya demostrado utilidad real;
- los casos residuales de miniatura blanca se hayan eliminado o se entiendan de forma trazable.

## 10. Recomendación final

La recomendación para este repositorio es implementar una migración frontend-only híbrida con estas características:

- **root principal**: `#feedbackReportRoot` visible y real;
- **preflight**: fuentes, recursos visuales, layout estable y validaciones previas;
- **motor principal**: capturador DOM robusto de la familia `html-to-image` o equivalente;
- **fallback**: motor de familia distinta de la familia `html2canvas` sin `foreignObject`;
- **salida final**: mantener `snapshot_png_dataurl` dentro del mismo `final_result.payload`;
- **política de error**: abandonar progresivamente el fallback transparente silencioso.

No se recomienda seguir remendando el serializer manual actual como estrategia principal porque el fallo dominante del sistema nace precisamente en esa arquitectura: `cloneNode(true)` + SVG manual con `<foreignObject>` + `Blob URL` + `Image`. Corregirlo “un poco más” obligaría a seguir invirtiendo en la parte más frágil del pipeline, mientras que el repositorio ya ofrece un punto de integración claro para sustituir solo la capa de snapshot sin tocar el resto del sistema que ya funciona.
