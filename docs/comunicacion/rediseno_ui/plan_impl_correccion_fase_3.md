# Plan de implementación correctiva · Fase 3 (loading + feedback final + autoentrega + parity visual fuerte)

## 1. Objetivo de la fase
- Resolver cierre de flujo final: transición limpia a loading, parity visual real con negociación y feedback final alineado.
- Eliminar entrega manual y activar autoentrega con notificación tipo toast.

**Cierre esperado de fase:**
- Sin pantalla intermedia rara al enviar.
- Loading en fondo blanco limpio sin card shell.
- Feedback final con estilo equivalente a negociación y autoentrega confirmada.

## 2. Alcance exacto
### Entra en esta fase
- eliminar visibilidad de `screenUploading`.
- mover/sacar loading de encuadre `communication-card`.
- rediseñar report final con patrón de negociación (`.fb-*` equivalente).
- quitar acciones manuales export/entrega.
- activar autoentrega al obtener report.
- mostrar toast de guardado (patrón negociación).

### No entra todavía
- cambios de contrato backend fuera de lo necesario para payload final existente.
- nuevas métricas avanzadas no requeridas por parity visual.

## 3. Problemas que esta fase corrige
- flash de pantalla intermedia al pulsar `Enviar y evaluar`.
- loading encerrado en card (sin sensación de escena limpia).
- feedback final con estilo distinto a negociación.
- dependencia de botones manuales para exportar/entregar.
- falta de confirmación UX equivalente a `Resultados guardados`.

## 4. Archivos que se tocarán
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `backend/comunicacion_app/report_view.js`
- `docs/comunicacion/rediseno_ui/11-diagnostico-transicion-a-loading-y-pantalla-intermedia-rara.md` (estado aplicado)
- `docs/comunicacion/rediseno_ui/12-extraccion-exacta-feedback-negociacion-y-entrega-final.md` (mapping aplicado)

## 5. Cambios exactos por archivo

### `backend/comunicacion_app/index.html`
- añadir:
  - `#finalSaveToast` para confirmación visual de autoentrega.
  - estructura de loading fuera del shell-card (o en rama visual sin card).
- modificar:
  - `screenProcessing` para render full-screen limpio.
  - `screenReport` para dejar solo raíz del informe (sin acciones manuales).
- mover/refactorizar:
  - reubicar `feedback-loading-layout` en contenedor de vista completa.
- eliminar:
  - `screenUploading` como pantalla visible al usuario.
  - botones `#exportReportJsonBtn`, `#exportReportHtmlBtn`, `#exportReportPngBtn`, `#emitFinalResultBtn`.
  - panel textual `#finalResultStatusPanel` si se sustituye por toast.
- conservar:
  - `#reportPlaceholderRoot` o su equivalente como host del informe.

### `backend/comunicacion_app/app.js`
- añadir:
  - `showCommunicationView(mode)` (patrón `showFeedbackView(mode)` de negociación).
  - `showFinalSaveToast()` / `hideFinalSaveToast()` equivalente negociación.
- modificar:
  - `sendAndEvaluate()` para transición directa a loading final sin paso intermedio visible.
  - `fetchEvaluationReport()` para disparar autoentrega tras render de informe.
- mover/refactorizar:
  - encapsular ciclo final: render report + emit final + esperar ACK + toast.
- eliminar:
  - dependencia funcional de click manual en `emitFinalResultBtn`.
  - mensajes “resultado final se habilitará...” en panel persistente.
- conservar:
  - funciones de payload/hash/correlation/ACK ya implementadas (`emitCommunicationFinalResultLifecycle`, hash helpers).

### `backend/comunicacion_app/styles.css`
- añadir:
  - estilos de vista full-screen para loading/report final.
  - estilos toast éxito inspirados en `.final-save-toast` negociación.
- modificar:
  - neutralizar card shell en processing/report (sin borde/sombra/radio contenedor externo).
  - alinear tipografía, espaciados, escala de cards y semáforos al patrón negociación.
- mover/refactorizar:
  - aislar estilos legacy `.comm-*` no alineados y priorizar bloque parity final.
- eliminar:
  - reglas que fuerzan encuadre de loading dentro de `.communication-card`.
- conservar:
  - animaciones floating útiles si ya son parity.

### `backend/comunicacion_app/report_view.js`
- añadir:
  - renderer parity con estructura visual equivalente a `FeedbackReportView.renderReport()`.
- modificar:
  - migrar de `.comm-v3-*` hacia arquitectura de secciones/tarjetas tipo `.fb-*` (adaptada a comunicación).
- mover/refactorizar:
  - separar capa de datos de capa de presentación para facilitar parity.
- eliminar:
  - markup que dificulte jerarquía visual de negociación.
- conservar:
  - utilidades de serialización HTML/PNG (adaptadas al nuevo markup).

### `docs/comunicacion/rediseno_ui/11-diagnostico-transicion-a-loading-y-pantalla-intermedia-rara.md`
- añadir:
  - sección “implementado en Fase 3” con estado final.
- modificar:
  - marcar causas corregidas.
- mover/refactorizar:
  - N/A
- eliminar:
  - N/A
- conservar:
  - análisis causal original.

### `docs/comunicacion/rediseno_ui/12-extraccion-exacta-feedback-negociacion-y-entrega-final.md`
- añadir:
  - mapping de adopción final de piezas `toast + autoentrega + estilo report`.
- modificar:
  - tabla de reutilización con estado final (aplicado/no aplicado).
- mover/refactorizar:
  - N/A
- eliminar:
  - N/A
- conservar:
  - extracción base completa.

## 6. Cambios de estilo de esta fase
- Referencia negociación:
  - `feedbackLoadingScreen`, `feedback-loading-layout`, `feedback-card`, `final-save-toast`.
  - plantilla visual de `feedback_report_view.js` (`.fb-card`, `.fb-header`, `.fb-result`, `.fb-recommendations`).
- Patrones exactos a replicar/adaptar:
  - fondo blanco continuo,
  - tarjetas con borde suave/radio 16,
  - jerarquía tipográfica de títulos,
  - semáforos verde/ámbar/rojo,
  - grid de tarjetas y recomendaciones.
- Correcciones de color/fondo/sombra/radio/espaciado/tipografía:
  - eliminar encuadre externo tipo card para loading/report.
  - usar escala visual consistente con negociación.
- Visuales que deben desaparecer:
  - acciones manuales de export/entrega.
  - panel de estado persistente sustituto del toast.
- Estado esperado al cierre:
  - parity visual fuerte del cierre de flujo con negociación.

## 7. Nuevas piezas a introducir
- ids:
  - `#finalSaveToast` (si no existe en comunicación).
  - `#communicationLoadingScreen` / `#communicationReportScreen` si se implementa con patrón por vista.
- clases:
  - `.final-save-toast`, `.final-save-toast.visible`, `.feedback-screen` variante comunicación.
- funciones:
  - `showCommunicationView(mode)`
  - `showFinalSaveToast()` / `hideFinalSaveToast()`
- handlers/listeners:
  - listener de ACK `final_result_saved` conectado al toast.
- estado nuevo:
  - `state.final_delivery.toast_visible` (opcional).

## 8. Piezas reutilizadas desde negociación
- `showFeedbackView(mode)` como patrón de cambio de vistas (`interfaz_usuario_app/app.js`).
- `showFinalSaveToast`/`hideFinalSaveToast` (`interfaz_usuario_app/app.js` + `index.html` CSS).
- composición de `FeedbackReportView.renderReport()` (`interfaz_usuario_app/feedback_report_view.js`).
- **tipo de reutilización:** combinación de copia adaptada + referencia exacta de jerarquía visual.

## 9. Orden interno recomendado de implementación
1. Quitar visibilidad de `screenUploading` y fijar transición directa a loading.
2. Reestructurar contenedor de loading para eliminar card framing.
3. Implementar `showCommunicationView(mode)` para separar app/loading/report/error.
4. Eliminar acciones manuales del report UI.
5. Activar autoentrega en `fetchEvaluationReport()`.
6. Añadir toast y conectarlo a ACK de guardado.
7. Migrar `report_view.js` a parity visual negociación.
8. Validación de extremo a extremo.

## 10. Invariantes / no romper
- `sendAndEvaluate` debe seguir disparando evaluación real.
- polling de evaluación debe mantener estados de error/éxito.
- generación de payload final/ACK correlacionado no debe perderse.
- render del informe debe seguir exportable internamente (aunque no haya botones manuales).

## 11. Riesgos específicos
- Técnicos: carreras entre render report y autoentrega/ACK.
- UX: toast no visible por z-index o timing.
- Integración: contenedor embebido sin `parent_origin` válido para ACK.
- Regresión: eliminación de botones rompe fallback de depuración.

## 12. Estrategia de fallback
- Fallback aceptable:
  - mantener export interno sin botones (API/debug hooks) mientras UI final oculta acciones manuales.
  - si ACK no llega, mostrar toast de “resultado listo localmente” no bloqueante.
- Puede esperar a fase siguiente:
  - microajustes de copy/tipografía si ya hay parity funcional+visual alta.
- No puede salir mal:
  - no debe reaparecer pantalla intermedia rara ni quedar entrega exclusivamente manual.

## 13. Validaciones / checks manuales
- Al pulsar `Enviar y evaluar`:
  - no aparece vista intermedia textual.
  - se ve loading limpio full-screen.
- Al completarse evaluación:
  - se muestra informe final con estilo parity.
  - no hay botones de export/entrega manual.
- Autoentrega:
  - se emite ciclo final automáticamente.
  - si llega ACK, aparece toast de guardado.
- Embebido/no embebido:
  - comportamiento estable en ambos contextos.

## 14. Criterio de cierre de fase
La fase se cierra cuando:
1. Desaparece la transición rara y loading queda en fondo blanco sin card externa.
2. Feedback final queda visualmente alineado con negociación (estructura y estilo).
3. La entrega final se ejecuta automáticamente y se notifica con toast.
4. El flujo end-to-end (grabar → enviar → loading → feedback) funciona sin pasos manuales de cierre.
