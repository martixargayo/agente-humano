# Plan de implementación correctiva · Fase 1 (limpieza estructural y eliminación de ruido visual)

## 1. Objetivo de la fase
- Resolver la contaminación visual transversal causada por el shell global de `comunicacion`.
- Eliminar cabeceras/copys redundantes en setup, AIDA, recording, review y report.
- Dejar una base visual seca y limpia (fondo/superficies) para que Fase 2 y 3 puedan aplicar parity real con negociación.

**Cierre esperado de fase:**
- No aparecen `Comunicación · Captura`, `#activityTitle`, `#activitySubtitle` (o equivalentes) en pantallas de flujo.
- No quedan títulos descriptivos redundantes por pantalla cuando duplican el contexto del paso.

## 2. Alcance exacto
### Entra en esta fase
- Limpieza de shell superior y textos redundantes.
- Condicionamiento de render global para evitar repintado transversal de títulos/subtítulos.
- Ajustes base de layout/superficies para fondo blanco limpio.

### No entra todavía
- Port completo de primera pantalla al patrón `entryOverlay` (Fase 2).
- Reorganización profunda de recording AV + controlar Grabar/Detener final (Fase 2).
- Eliminación de transición intermedia upload + rediseño loading/report final (Fase 3).

## 3. Problemas que esta fase corrige
- Repetición de cabecera superior en todas las pantallas.
- Copy de contexto duplicado/noise (`setupContextSummary`, `aidaContextSummary`) forzado por `renderApp()`.
- Títulos de panel no esenciales que recargan UI.
- Persistencia de shell/card en vistas donde debe quedar lectura limpia.

## 4. Archivos que se tocarán
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `docs/comunicacion/rediseno_ui/10-limpieza-de-cabeceras-y-textos-sobrantes-en-comunicacion.md` (actualización de checklist post-ejecución)

## 5. Cambios exactos por archivo

### `backend/comunicacion_app/index.html`
- añadir:
  - contenedor opcional de encabezado por pantalla (si se requiere) con clase togglable (`.screen-local-header`), no global.
- modificar:
  - estructura de `<header class="communication-header">` para que no sea cabecera persistente de todo el flujo.
- mover/refactorizar:
  - mover texto esencial al interior de cada pantalla solo cuando sea estrictamente necesario.
- eliminar:
  - `.eyebrow` con texto `Comunicación · Captura`.
  - `#activityTitle` y `#activitySubtitle` si no aportan en el paso actual.
  - encabezados repetitivos en `screenAidaPrep`, `screenRecording`, `screenReview`, `screenReport`.
- conservar:
  - IDs funcionales de navegación, captura y evaluación.

### `backend/comunicacion_app/app.js`
- añadir:
  - helper `shouldRenderGlobalHeader(screen)` o eliminación total de dependencia de header global.
- modificar:
  - `renderApp()` para no escribir siempre en `activityTitle`, `setupContextSummary`, `aidaContextSummary`.
- mover/refactorizar:
  - separar “render de estado funcional” de “render de copy decorativo”.
- eliminar:
  - escrituras de texto transversal que contaminen pantallas.
- conservar:
  - `SCREEN_ORDER`, navegación de estados, handlers de captura/evaluación.

### `backend/comunicacion_app/styles.css`
- añadir:
  - reglas de limpieza visual para pantallas sin header persistente.
- modificar:
  - espaciados/paddings verticales al retirar cabecera.
- mover/refactorizar:
  - desacoplar estilos de `.communication-header` de la estructura principal.
- eliminar:
  - estilos que solo servían al header global (`.eyebrow`, `.communication-subtitle`) cuando ya no se usen.
- conservar:
  - tokens de color `--comm-*` y estilos funcionales de controles.

### `docs/comunicacion/rediseno_ui/10-limpieza-de-cabeceras-y-textos-sobrantes-en-comunicacion.md`
- añadir:
  - checklist “aplicado en Fase 1” por pantalla.
- modificar:
  - estado de cada nodo: pendiente → resuelto.
- mover/refactorizar:
  - N/A
- eliminar:
  - N/A
- conservar:
  - inventario base como evidencia.

## 6. Cambios de estilo de esta fase
- Referencia de negociación a tomar:
  - principio de vistas limpias sin encabezado persistente en loading/report.
- Patrones a replicar/adaptar:
  - separación por pantalla sin texto global fijo.
- Correcciones visuales concretas:
  - fondo blanco continuo.
  - reducción de cajas y textos introductorios redundantes.
  - ritmo vertical más compacto (menos “cabecera + subtítulo + panel”).
- Shell/cards/headers que deben desaparecer en Fase 1:
  - header global superior en el flujo principal.
- Estado de alineación esperado al cerrar fase:
  - limpieza estructural lograda, aunque parity fina de permisos/feedback queda para Fase 2/3.

## 7. Nuevas piezas a introducir
- ids:
  - opcional `#screenLocalHeader` si se requiere encabezado contextual mínimo.
- clases:
  - `.is-headerless-flow`, `.screen-local-header` (si aplica).
- funciones:
  - `renderScreenCopy(screen)` o `shouldRenderGlobalHeader(screen)`.
- handlers/listeners:
  - no nuevos obligatorios; solo reutilización del render actual.
- estado nuevo:
  - opcional `state.ui.header_mode` (`global`/`local`/`none`).

## 8. Piezas reutilizadas desde negociación
- `show/hide` de vistas sin header persistente (concepto) desde `interfaz_usuario_app/app.js`.
- criterio de pantalla limpia en loading/report desde `interfaz_usuario_app/index.html`.
- **tipo de reutilización:** referencia de arquitectura, no copia literal aún.

## 9. Orden interno recomendado de implementación
1. Retirar/condicionar header global en `index.html`.
2. Ajustar `renderApp()` para no reinyectar textos transversales.
3. Limpiar títulos/copy redundante por pantalla (setup/AIDA/recording/review/report).
4. Corregir CSS de espaciado y superficies tras la limpieza.
5. Validar checklist visual completa de Fase 1.

## 10. Invariantes / no romper
- No romper transición de pantallas por `SCREEN_ORDER`.
- No romper permisos AV ni selectors de dispositivos.
- No romper botones de flujo (`Continuar`, `Grabar`, `Enviar y evaluar`).
- No romper render de report placeholder/final.

## 11. Riesgos específicos
- Técnicos: dependencia accidental de nodos eliminados en `renderApp()`.
- UX: dejar pantalla demasiado vacía sin jerarquía mínima.
- Integración: CSS huérfano o gaps tras retirar header.
- Regresión: desalineación móvil por cambios de spacing.

## 12. Estrategia de fallback
- Fallback aceptable: mantener encabezado mínimo local por pantalla (1 línea) si quitar todo rompe legibilidad.
- Puede esperar a fase siguiente: ajuste fino de composición recording y parity tipográfica.
- No puede salir mal: no debe reaparecer cabecera global contaminante en todo el flujo.

## 13. Validaciones / checks manuales
- Setup: no aparece `.eyebrow` ni `#activityTitle/#activitySubtitle`.
- AIDA: sin cabecera redundante superior.
- Recording: sin título/copy redundante heredado.
- Review: pantalla directa (vídeo + CTA), sin ruido textual.
- Report: sin cabecera superior heredada.
- Responsivo: verificar desktop + móvil sin saltos visuales.

## 14. Criterio de cierre de fase
La fase se cierra cuando:
1. La contaminación textual transversal desaparece de todas las pantallas objetivo.
2. El flujo funcional sigue intacto.
3. La base visual queda limpia para ejecutar parity de Fase 2 y Fase 3.
