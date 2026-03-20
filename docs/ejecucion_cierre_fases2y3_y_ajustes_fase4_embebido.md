# Cierre de Fases 2 y 3 + ajustes de Fase 4 (embebido)

## 1. Estado real antes de este turno

### Fase 2
Antes de este turno **no estaba cerrada**.

Lo que sí existía:
- identidad consolidada de bootstrap en frontend
- metadatos de sesión (`session_id`, `conversation_id`, `context_id`, etc.)
- un punto interno para `session-ready` como evento del navegador

Lo que faltaba:
- un `embed mode` explícito y mantenible
- diferencias reales de layout entre standalone y embebido
- mitigación de dependencias fullscreen rígidas en CSS
- base suficiente para que el iframe pudiera crecer sin depender de fullscreen puro

### Fase 3
Antes de este turno **estaba solo parcialmente implementada**.

Lo que sí existía:
- emisión semántica de `error` al padre para `session_busy`
- `targetOrigin` explícito
- ausencia de `postMessage("*")`

Lo que faltaba:
- capa común de mensajería iframe→padre
- mensaje `ready` real
- mensaje `height` real
- criterio explícito de emisión de `ready`
- una base clara para mensajería embebida orientada a sesión viva más allá de `session_busy`

### Fase 4
La base de `session_busy` ya existía, pero quedaban ajustes:
- limpieza de UX stale al salir de busy
- decisión explícita sobre `bootstrap` y `newConv` durante busy
- validación/documentación más clara de qué archivos pertenecían a fases previas

## 2. Qué se implementó ahora para cerrar Fase 2

### Modo embebido explícito
Se implementó un `embed mode` explícito en `backend/interfaz_usuario_app/app.js`.

#### Activación
El modo embebido se activa con esta prioridad:
1. query param `?embed=1|true|yes|on|embed`
2. query param `?embed=0|false|no|off` para forzar standalone
3. fallback automático a `window.parent !== window`

### Cambios de layout en embebido
Se añadieron overrides localizados en `backend/interfaz_usuario_app/index.html` para `html[data-embed-mode="1"]`:
- `html/body` dejan de forzar `height: 100%` + `overflow: hidden`
- `#mainApp` pasa a tener altura mínima real y padding inferior para convivir con la barra inferior
- `#stage` deja de ser estrictamente fixed y pasa a base absoluta dentro del flujo embebido
- `.bottom-bar` pasa a `position: sticky` en embebido
- `.feedback-screen` deja de ser `position: fixed` en embebido y puede crecer en altura
- `#feedbackReportScreen` y `#feedbackReportRoot` permiten crecimiento real del contenido
- `finish-negotiation-button` y `finish-confirm-popover` pasan a absolutas en embebido

### Qué no cambia en standalone
El comportamiento por defecto sigue siendo standalone.
Los overrides se aplican solo bajo `data-embed-mode="1"`.

## 3. Qué se implementó ahora para cerrar Fase 3

### Canal postMessage real
Se creó una capa común de mensajería embebida en `backend/interfaz_usuario_app/app.js` con:
- `buildEmbedEnvelope(...)`
- `emitEmbedMessage(...)`
- `emitParentEmbedError(...)`

Todos los mensajes:
- usan `targetOrigin = https://academia.gestionce.com`
- no usan `*`
- incluyen correlación basada en sesión viva

### Mensajes soportados tras este turno
#### `ready`
Se emite solo cuando:
- `embed mode` está activo
- hay identidad consolidada (`session_id` real)
- `scenarioReady === true`
- la sesión no ha emitido ya `ready` para esa correlación bootstrap

Payload de `ready`:
- `route`
- `reason`
- `session_bootstrap_state`
- `existing_session`
- `trace_count`
- `embed_mode`

#### `height`
Se emite realmente al padre.
La altura se calcula a partir de las superficies visibles (`mainApp`, loading, report, error) y de métricas de documento (`scrollHeight`, `offsetHeight`, `getBoundingClientRect`).

Se agenda en:
- cambios de vista
- cambios de UI
- cambios de estado/reply
- render del informe
- resize/focus/pageshow/visibilitychange
- emisión de `ready`

#### `error`
Se mantiene y se normaliza sobre la nueva capa común.
Hoy queda soportado explícitamente para `session_busy`.

### Qué no se implementó en esta ronda de Fase 3
- `final_result`
- `final_result_available`

Esos mensajes siguen pendientes para la Fase 5 y no se mezclaron en este cierre.

## 4. Ajustes aplicados sobre Fase 4

### Limpieza de UI stale al salir de busy
Se añadió `cleanupSessionBusyUx(...)` para limpiar/restaurar:
- `entryError`
- `statusText`
- `replyContainer`
- `feedbackErrorMessage`
- `meta`

### Decisión sobre `bootstrap` y `newConv` durante busy
Se decidió **bloquear ambas acciones** mientras la sesión siga ocupada.

Motivo:
- evita que el usuario use esos botones como escape manual del lock
- mantiene la semántica de “una sesión ocupada no se esquiva inventando otra por UI”
- evita incoherencias de correlación en el iframe embebido

### Aclaración sobre archivos backend (`models.py` / `services.py`)
Los cambios en:
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`

**no pertenecen a este cierre de Fases 2 y 3**.
Venían de la fase previa de alineación con bootstrap/identidad real.
En este turno no se tocaron.

## 5. Archivos modificados en este turno

- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/index.html`
- `docs/ejecucion_cierre_fases2y3_y_ajustes_fase4_embebido.md`

## 6. Cómo se activa embed mode

Ejemplos:
- `https://simulador.gestionce.com/interfaz_usuario/slug?embed=1`
- si no hay query param, estar dentro de iframe activa embed mode por fallback
- `?embed=0` fuerza standalone aunque se abra dentro de un frame de pruebas

## 7. Qué mensajes postMessage quedan soportados realmente tras este turno

- `ready`
- `height`
- `error`

Pendientes para Fase 5:
- `final_result`
- `final_result_available`

## 8. Cómo se validó

### Validación ejecutada en este entorno
- `node --check backend/interfaz_usuario_app/app.js`
- `! rg -n "postMessage\\(\\s*['\"]\\*['\"]" backend/interfaz_usuario_app/app.js`
- `rg -n "data-embed-mode|emitEmbedMessage\\('ready'|emitEmbedMessage\\('height'|session_busy|cleanupSessionBusyUx|getActiveSessionBusyState\\(\\)" backend/interfaz_usuario_app/app.js backend/interfaz_usuario_app/index.html`
- revisión del diff para confirmar que los cambios quedaron acotados a Fase 2, Fase 3 y ajustes de Fase 4

### Validación manual reproducible recomendada
1. Abrir la URL standalone sin `embed` y confirmar que el layout se mantiene como antes.
2. Abrir la misma URL dentro de iframe o con `?embed=1` y confirmar que `document.documentElement.dataset.embedMode === '1'`.
3. Observar en el padre que llegan mensajes `ready` y `height` con `session_id` y correlación.
4. Forzar un `423 session_busy` en dos contextos para la misma sesión y comprobar:
   - bloqueo de UI
   - mensaje claro al usuario
   - lectura de `Retry-After`
   - limpieza posterior del estado stale al expirar o al recibir una respuesta válida
   - `postMessage` de tipo `error` al padre con `code = session_busy`

## 9. Estado de la Fase 5 en esta rama

En una iteración posterior sobre esta misma rama se completó el cierre funcional que aquí quedaba pendiente:

- `final_result_available`
- `final_result`
- exportación del informe a HTML
- exportación del informe a JSON
- exportación PNG del informe mediante rasterización en cliente
- acciones visibles de descarga dentro de la pantalla final del reporte

La validación reproducible de ese cierre quedó cubierta por tests de serving/regresión sobre los assets públicos y por checks sintácticos del frontend.
