# Guía superdetallada: `entryOverlay` (negociación) + blueprint para extenderlo con cámara

## 1) Dónde está el código fuente exacto

El bloque HTML base que monta esta pantalla vive en:

- `backend/interfaz_usuario_app/index.html` (markup del overlay y nodos con `id`).
- `backend/interfaz_usuario_app/index.html` (CSS de clases `.entry-*`).
- `backend/interfaz_usuario_app/app.js` (lógica de estado, permisos, refresco de dispositivos, habilitación del CTA y transición al flujo principal).

> Importante: el HTML inicial del archivo **no siempre coincide literalmente con lo que ves en runtime** en DevTools, porque `app.js` modifica textos, clases, contenido interno y estado del botón según permisos/modo/escenario.

---

## 2) Anatomía exacta de la UI (línea por línea conceptual del bloque que compartiste)

A continuación, desgloso cada pieza del fragmento que pasaste, cómo se crea y qué función cumple.

### 2.1 Contenedor principal

### `<div id="entryOverlay" class="entry-overlay" role="dialog" aria-modal="true">`

- `id="entryOverlay"`: llave principal para controlarlo desde JS (`ui.entryOverlay`).
- `class="entry-overlay"`: aplica layout de pantalla completa fija (`position: fixed`, `inset: 0`, centrado flex, fondo blanco, z-index alto).
- `role="dialog" aria-modal="true"`: accesibilidad; anuncia al lector de pantalla que es una capa modal de entrada.
- Estado visual de cierre: cuando se completa entrada, JS añade `.hidden` y después hace `display: none` tras 240ms para respetar transición.

### 2.2 Tabs de modo

### `entry-mode-tabs` + botones `entryModeTalk` / `entryModeWrite`

- El bloque se pinta como "pill switch" con fondo gris claro y tabs redondeadas.
- `entryModeTalk` inicia con `.active`; JS alterna `.active` y `aria-selected` según `entryMode`.
- `entryModeWrite` activa modo escritura sin requerir micrófono.
- Eventos:
  - click en `entryModeTalk` -> `setEntryMode(InputMode.TALK)`.
  - click en `entryModeWrite` -> `setEntryMode(InputMode.WRITE)`.

### 2.3 Card central

### `entry-card` + `entry-card-content`

- Card centrada con ancho máximo controlado (`min(460px, 92vw)`), borde suave, sombra y radio alto.
- `entry-card-content` organiza el contenido en columna para mantener estructura estable aunque cambien mensajes dinámicos.

### 2.4 Subtítulo dinámico

### `<p class="entry-subtitle" id="entrySubtitle">`

- En modo hablar, JS muestra mensajes de guía de permisos.
- En modo escribir, JS lo oculta (`entry-hidden`) para limpiar la pantalla.

### 2.5 Panel "Hablar" (`entryTalkContent`)

#### `entryDeviceLabel`

- Etiqueta visual "Dispositivos de audio" (uppercase/estilo de caption).
- Se oculta cuando todavía falta permiso de micrófono.

#### `entryDeviceSearch`

- Contenedor de estado de búsqueda/listado de micrófonos.
- JS cambia su `innerHTML` según estado:
  - Sin permiso: texto de instrucción para conceder acceso.
  - Con permiso: "Micrófonos detectados" + spinner.

#### `entryDeviceList`

- Lista accesible (`role="listbox"`) renderizada dinámicamente.
- Casos de render:
  - Sin permiso: bloque "Activa el micrófono...".
  - Con permiso pero vacío: "Ningún dispositivo conectado".
  - Con dispositivos: se crean botones `entry-device-option` con icono + nombre limpio + check.
- Cada opción guarda `data-device-id` y al click invoca selección (`setSelectedEntryDevice`).

#### `entryDeviceStatus`

- Mensaje de estado inferior con `aria-live="polite"`.
- JS alterna texto y clase `.error` por estado:
  - `prompt/unknown`: instrucción para activar permiso.
  - `denied`: error de permiso.
  - `granted` sin selección: error de no detección.
  - `granted` con selección: confirmación "puedes empezar".

### 2.6 Panel "Escribir" (`entryWriteContent`)

- Empieza oculto (`entry-hidden`) y se muestra sólo en modo escritura.
- Mantiene copy simple para explicar que no depende de micrófono.

### 2.7 Acciones (`entry-actions`) y CTA principal

### `<button id="startBtn" class="primary-btn">Empezar</button>`

- Es el CTA único del overlay.
- Su estado lo controla `renderEntryState()`:
  - Puede quedar deshabilitado por combinación de modo/permiso/dispositivo/escenario.
  - Texto dinámico:
    - "Activar micrófono" si modo hablar sin permiso.
    - "Cargando escenario…" si el usuario ya pidió entrar pero runtime aún no está listo.
    - "Empezar" en estado normal.

### 2.8 Error general (`entryError`)

- Canal para errores operativos (fallo en `getUserMedia`, no device válido, fallo de precalentamiento de captura, etc.).

### 2.9 Estado de escenario (`entryScenarioState`)

- Muestra readiness del avatar/escenario:
  - no listo: spinner visible + "Cargando escenario".
  - listo: spinner oculto + "Escenario cargado" + clase `.ready`.
- Este estado participa en gating del CTA final (`getCanEnterNow()` exige escenario listo).

---

## 3) Flujo funcional completo (orden de ejecución real)

## 3.1 Inicialización al cargar

1. IIFE `initInterfazUsuarioSession()` arranca bootstrap de sesión y runtime.
2. En paralelo funcional, ejecuta `bootstrapEntryDeviceBackground()`:
   - `syncMicPermissionState()` para leer estado de permiso inicial con Permissions API.
   - `refreshEntryDevices('bootstrap')` para enumerar dispositivos si procede.
   - `renderEntryDevices()` + `renderEntryState()`.
3. Fuerza modo inicial de entrada `TALK` (`setEntryMode(InputMode.TALK)`).
4. Programa refresco inmediato de dispositivos (`scheduleEntryDeviceRefresh('post-init', 0)`).

## 3.2 Render reactivo de la pantalla

`renderEntryState()` centraliza UI derivada de estado. Recalcula en cada evento relevante:

- Tabs activas/inactivas.
- Visibilidad de panel hablar/escribir.
- Subtítulo de permisos.
- Habilitación y texto de `startBtn`.
- Estado de escenario y spinner.
- Header de búsqueda/permiso.
- Mensaje de estado de dispositivo + clase error.

## 3.3 Solicitud de permisos

Cuando el usuario pulsa `startBtn` en modo hablar:

1. `handleStartEntry()` llama `validateTalkModeForEntry()`.
2. Si no hay permiso `granted`, `requestMicPermissionsForEntry()` ejecuta `getUserMedia(...)`.
3. Manejo fino de errores por `err.name`:
   - `NotAllowedError/SecurityError` -> permiso denegado.
   - `NotReadableError` -> dispositivo ocupado/lectura fallida.
   - `NotFoundError/OverconstrainedError` -> no hay mic compatible.
4. Tras intento, refresca lista (`refreshEntryDevices(...)`) y rerender.

## 3.4 Enumeración y selección de dispositivos

`refreshEntryDevices()`:

- Usa `enumerateDevices()`.
- Filtra `audioinput` y normaliza etiquetas (`toUiAudioInputDevices`).
- Deduplica por `groupId + labelKey` para evitar duplicados comunes de browser.
- Intenta preservar selección previa (`pickReplacementDevice`).
- Persiste selección en `localStorage` (`LAST_DEVICE_STORAGE_KEY`).
- Vuelve a renderizar lista/estado/selector inferior.

## 3.5 Entrada final al flujo principal

- Si modo escribir: entra directo.
- Si modo hablar: precalienta captura (`startVoiceCapture`) antes de cerrar overlay para evitar sensación de "click muerto".
- `finalizeEntry()` aplica transición:
  - añade clase `.hidden`.
  - tras 240ms: `style.display = 'none'`.

## 3.6 Sincronización continua

Además del click de usuario, se mantiene actualización por:

- polling cada 3s cuando overlay visible.
- evento `navigator.mediaDevices.devicechange`.
- `focus`, `pageshow`, `visibilitychange`.
- cambio de permiso (`status.onchange` de Permissions API).

---

## 4) Relación directa con tu objetivo: duplicarlo "idéntico" para Comunicación + añadir cámara

Si quieres que la primera pantalla de Comunicación sea **idéntica en estética y procedimiento**, la vía más segura es copiar este patrón 1:1 y extenderlo a AV.

## 4.1 Qué mantener idéntico

- Estructura del overlay y card.
- CTA único `startBtn` con copy dinámico.
- Estado de escenario separado abajo.
- Patrón de mensajes inline (`entryDeviceStatus`) + error general (`entryError`).
- Máquina de estados renderizada desde una única función `renderEntryState`.

## 4.2 Extensión mínima para cámara (sin romper UX existente)

Añade un segundo bloque simétrico al de audio:

- `entryCameraLabel`
- `entryCameraSearch`
- `entryCameraList`
- `entryCameraStatus`

Y estados nuevos:

- `entryCameraPermissionStatus` (`unknown|prompt|granted|denied`)
- `availableVideoInputDevices`
- `selectedEntryCameraDeviceId`

Permisos:

- Recomendación UX: pedir audio+video en una sola acción de CTA para reducir fricción de prompts consecutivos.
- Constraints sugeridas:
  - audio: mismas del flujo actual.
  - video: `{ facingMode: 'user' }` + `deviceId exact` si hay selección.

Gating de CTA en modo hablar AV:

- habilitar "Empezar" sólo si:
  - escenario listo,
  - permiso mic ok + dispositivo mic seleccionado,
  - permiso cámara ok + dispositivo cámara seleccionado (si tu producto exige cámara obligatoria).

Si cámara es opcional, separa:

- estado "requerido" vs "opcional" en función de configuración de escenario.

---

## 5) Mapa rápido de funciones clave que debes replicar/adaptar

- `renderEntryState()` -> corazón visual de todo el overlay.
- `renderEntryDevices()` -> lista interactiva de dispositivos de entrada.
- `requestMicPermissionsForEntry()` -> negociación de permisos con manejo fino de errores.
- `refreshEntryDevices()` + `scheduleEntryDeviceRefresh()` -> coherencia frente a cambios de hardware/browser.
- `validateTalkModeForEntry()` -> validación previa al "start".
- `handleStartEntry()` + `finalizeEntry()` -> transición robusta al flujo principal.

Para cámara, crea versiones paralelas (`...Camera...`) y finalmente un `validateAvModeForEntry()` que orqueste ambos.

---

## 6) Checklist de implementación para que te quede "idéntica"

1. Copiar HTML y CSS de `entryOverlay` exactamente.
2. Reusar nombres de clases para conservar spacing/tipografía/sombras.
3. Mantener una sola función `renderEntryState` como fuente de verdad de UI.
4. Reproducir mismo patrón de estados y textos operativos.
5. No cerrar overlay hasta que el escenario esté listo (`scenarioReady`) y validación de dispositivos/prompt esté completa.
6. Aplicar la misma transición `.hidden` + `display:none` diferida.
7. Añadir capa cámara como bloque hermano del audio, con misma semántica ARIA y feedback.

Con esto, tu pantalla de Comunicación va a sentirse prácticamente clonada en look&feel y comportamiento, incorporando cámara sin degradar el flujo de permisos.
