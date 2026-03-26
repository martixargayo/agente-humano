# 09 · Extracción exacta de pantalla de permisos de negociación

## 1) Objetivo del doc
Extraer con precisión quirúrgica la primera pantalla de permisos/entrada de `interfaz_usuario` (negociación), para reutilizar su patrón visual y funcional en `comunicacion` sin aproximaciones vagas.

## 2) Archivos inspeccionados
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`

## 3) Evidencia exacta encontrada en el repo

### 3.1 HTML exacto de la pantalla de permisos (negociación)
Bloque principal de entrada/permisos (`#entryOverlay`):

```html
<div id="entryOverlay" class="entry-overlay" role="dialog" aria-modal="true">
  <div class="entry-mode-tabs" role="tablist" aria-label="Modo de acceso">
    <button id="entryModeTalk" class="entry-mode-tab active" role="tab" aria-selected="true">Hablar</button>
    <button id="entryModeWrite" class="entry-mode-tab" role="tab" aria-selected="false">Escribir</button>
  </div>
  <div class="entry-card">
    <div class="entry-card-content">
      <p class="entry-subtitle" id="entrySubtitle">Prepara tu dispositivo para hablar.</p>

      <div id="entryTalkContent" class="entry-talk-content">
        <p id="entryDeviceLabel" class="entry-device-label">Dispositivos de audio</p>
        <div id="entryDeviceSearch" class="entry-device-search" aria-live="polite">
          <span>Buscando dispositivos de audio</span>
          <span class="entry-device-search-spinner" aria-hidden="true"></span>
        </div>
        <div id="entryDeviceList" class="entry-device-list" role="listbox" aria-label="Seleccionar dispositivo de audio"></div>
        <div id="entryDeviceStatus" class="entry-device-status" aria-live="polite"></div>
      </div>

      <div id="entryWriteContent" class="entry-write-content entry-hidden">
        <p>Entrarás en modo escritura.</p>
        <p>Podrás empezar aunque no haya micrófono disponible.</p>
      </div>

      <div class="entry-actions">
        <button id="startBtn" class="primary-btn">Empezar</button>
      </div>

      <div id="entryError" class="error-text" aria-live="polite"></div>
    </div>
  </div>

  <div id="entryScenarioState" class="entry-scenario-state" aria-live="polite">
    <span id="entryScenarioSpinner" class="entry-scenario-spinner" aria-hidden="true"></span>
    <span id="entryLoadingText">Cargando escenario</span>
  </div>
</div>
```

### 3.2 CSS exacto que define la experiencia
Clases base de overlay/entrada en `index.html` inline style:
- `.entry-overlay` (overlay fullscreen, fondo blanco, centrado)
- `.entry-mode-tabs`, `.entry-mode-tab`
- `.entry-card`, `.entry-card-content`
- `.entry-subtitle`
- `.entry-device-list`, `.entry-device-option`, `.entry-device-status`
- `.entry-actions`, `.primary-btn`
- `.entry-scenario-state`, `.entry-scenario-spinner`

Comportamiento visual clave:
- Es una capa dedicada de entrada (`position: fixed`, ocupa viewport completo).
- El CTA es único (`#startBtn`) y cambia label según estado.
- El estado de escenario (`#entryScenarioState`) está dentro de la misma escena de permisos.

### 3.3 JS exacto (ids, funciones, handlers)

**IDs capturados en `ui` map:**
- `entryOverlay`, `entryModeTalk`, `entryModeWrite`, `entryTalkContent`, `entryWriteContent`
- `entrySubtitle`, `entryDeviceLabel`, `entryDeviceSearch`, `entryDeviceList`, `entryDeviceStatus`
- `startBtn`, `entryError`, `entryScenarioState`, `entryScenarioSpinner`, `entryLoadingText`

**Funciones que renderizan/actualizan la pantalla:**
- `renderEntryState()`
  - Alterna tabs hablar/escribir.
  - Cambia `#entrySubtitle` según permisos.
  - Habilita/deshabilita `#startBtn` con `getEntryModeStartEnabled()` y `entryInProgress`.
  - Cambia texto del CTA:
    - `Cargando escenario…`
    - `Activar micrófono`
    - `Empezar`
  - Actualiza estado de escenario (`#entryLoadingText`, spinner, clase `ready`).
  - Actualiza textos de estado de permiso (`#entryDeviceStatus`).
- `renderEntryDevices()`
  - Pinta lista de dispositivos y selección.
- `requestMicPermissionsForEntry()`
  - Solicita permiso de mic.
- `refreshEntryDevices()`
  - Enumera dispositivos tras permisos.

**Handler principal CTA:**
- `ui.startBtn.addEventListener('click', ...)`.
- Flujo real:
  1. Si no hay permisos en TALK, pide permisos.
  2. Actualiza estado/listado.
  3. Si escenario listo + condiciones satisfechas, cierra overlay y entra al runtime.

## 4) Diagnóstico del estado actual
- Negociación tiene una pantalla de entrada **atómica**: una sola capa, un solo CTA, estado explícito de permisos + readiness.
- Comunicación hoy tiene setup dentro de `communication-card` + cabecera global + copy extra + selects + botones secundarios, lo que rompe la “entrada limpia” buscada.

## 5) Extracción exacta de referencia de negociación aplicable a comunicación

### Pieza canónica a replicar
- Patrón `entry-overlay + entry-card + CTA único + estado contextual`.

### Diferencia funcional inevitable
- Negociación gestiona **solo audio input**.
- Comunicación necesita **audio + video** y preview.

## 6) Tabla de reutilización

| Pieza | Archivo origen | Reutilizar tal cual / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `#entryOverlay` concepto de capa de entrada | `interfaz_usuario_app/index.html` | Adaptar | Comunicación es multipista AV | `comunicacion_app/index.html` setup screen |
| `#startBtn` CTA único | `interfaz_usuario_app/index.html` + `app.js` | Reutilizar lógica, adaptar texto | Patrón de CTA dinámico ya probado | `setupPrimaryBtn` refactor a CTA único |
| `renderEntryState()` patrón de estado UI | `interfaz_usuario_app/app.js` | Adaptar | Estados difieren (audio vs audio+video) | Nueva función equivalente en `comunicacion_app/app.js` |
| Mensajería de estado de permisos | `renderEntryState()` | Adaptar | En comunicación hay cámara + micro | `setupStatusText` y banners |
| Tabs Hablar/Escribir | `entryModeTalk/Write` | Descartar | No aplica al flujo de comunicación | N/A |

## 7) Tabla de intervención futura por archivo

| Archivo | Qué tocar | Qué eliminar | Qué conservar | Riesgo |
|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | Reestructurar `screenSetup` a patrón overlay limpio | Copy redundante + duplicaciones de cabecera | IDs de dispositivos y preview (`videoDeviceSelect`, `audioDeviceSelect`, `setupPreviewVideo`) | Riesgo medio por dependencias de handlers existentes |
| `backend/comunicacion_app/app.js` | Crear render de estado tipo `renderEntryState` | Mensajes duplicados por banner + subtítulo | Funciones de permisos y device discovery actuales | Riesgo bajo-medio |
| `backend/comunicacion_app/styles.css` | Introducir visual de entrada equivalente | Estilo de card/cabecera general para setup | Tokens base (`--comm-*`) | Riesgo medio por cascada CSS |

## 8) Criterio claro de cómo debe quedar después
- Primera pantalla de comunicación debe percibirse como una **pantalla de acceso/permisos** (no “pantalla de app con cabecera + textos de contexto”).
- Debe existir **CTA principal único** con estados dinámicos.
- Debe mostrar estado de permisos/dispositivos sin copy redundante.
- Debe mantener compatibilidad funcional con cámara+mic y preview.
