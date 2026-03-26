# 03 · Pantalla de grabación rediseñada (AIDA + self-view + monitorización viva)

## 1) Objetivo del doc
Definir con precisión la pantalla de grabación objetivo, manteniendo lógica base de captura local pero rediseñando la experiencia visual y de control para que sea coherente con negociación.

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`

## 3) Evidencia exacta encontrada en repo
- `screenRecording` actual: video grande (`#recordingVideo`), indicador `#recordingIndicator`, botón `#stopRecordingBtn`.
- Cambio de dispositivos en caliente ya existe de forma básica en comunicación:
  - listeners `videoDeviceSelect.change` y `audioDeviceSelect.change`.
  - reabre stream con `openPreviewStream()`.
- En negociación existe selector avanzado de audio con:
  - `#audioDeviceSelector`, `#audioDevicePopover`, `audio-device-option`.
  - lógica de cambio en caliente `handleAudioDeviceChangeRequest()` + `restartVoiceCaptureAfterDeviceSwitch()`.
- `startRecordingTimer()` en comunicación hace `renderApp()` cada 250ms (dato importante para doc 07/flicker).

## 4) Diagnóstico del estado actual
- Falta guía de contenido en grabación (AIDA no visible).
- Falta panel de monitorización viva (audio/video health + waveform).
- El control de dispositivos es funcional pero poco usable y visualmente débil.

## 5) Referencia visual/técnica exacta
- Referencia técnica para cambio en caliente: flujo de negociación (popover + switch-safe + toasts).
- Referencia visual de interacción viva: estados activos en barra de negociación (`input-orb`, selector, estado).

## 6) Propuesta detallada de cómo debería quedar

### 6.1 Composición de pantalla
- Área principal (centro): guía AIDA en 2x2, modo lectura (contenido escrito en paso anterior).
- Columna derecha: self-view pequeña persistente.
- Barra de control inferior:
  - botón `Grabar` / `Detener` (según estado),
  - botón `Gestionar micrófono y cámara` (abre popover dual),
  - ondas de audio,
  - indicadores vivos AV.

### 6.2 Monitorización continua (sensación de sistema vivo)
- Badge `Micrófono` y badge `Cámara`:
  - verde = OK,
  - rojo = KO.
- Microanimación sutil (pulse o dot-live) cuando stream activo.
- Waveform/barras de audio con actualización periódica.

### 6.3 Gestión de dispositivos
- No usar `<select>` directo en UI final.
- Reutilizar patrón popover moderno estilo negociación:
  - lista principal (dispositivo activo),
  - lista secundaria (otros dispositivos),
  - acción de permisos cuando aplique.

## 7) Layout detallado
- Grid desktop recomendado:
  - `main` 2fr (AIDA),
  - `side` 1fr (self-view + estado).
- Self-view en card compacta, sticky en desktop.
- Barra inferior full-width dentro del card principal para no “flotar suelta”.
- Evitar sobrecarga: máximo 3 capas de información simultánea.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `startRecording()` / `stopRecording()` | `backend/comunicacion_app/app.js` | Reutilizar | núcleo de captura actual válido | motor de grabación |
| `recordingIndicator` | `backend/comunicacion_app/index.html` | Adaptar | sirve como base de timer live | badge de grabación |
| `audio-device-popover` patrón | `backend/interfaz_usuario_app/index.html` | Adaptar | UX moderna probada | gestión AV en grabación |
| `handleAudioDeviceChangeRequest()` patrón | `backend/interfaz_usuario_app/app.js` | Adaptar | cambio en caliente robusto | switch de mic/cam |
| `video-frame` full | `backend/comunicacion_app/styles.css` | Adaptar | ahora self-view debe ser mini | panel lateral |
| `screenRecording` actual simple | `backend/comunicacion_app/index.html` | Descartar (estructura) | insuficiente para objetivo | layout nuevo |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | markup `screenRecording` | ids de video si se reaprovechan | estructura de video único + botón único | grid AIDA + self-view + control bar | Medio |
| `backend/comunicacion_app/app.js` | render de recording, estado capture | recorder y stream base | dependencia UI en selects visibles | estado AV health + waveform + popover handlers | Alto |
| `backend/comunicacion_app/styles.css` | estilos recording | tokens de botones | layout actual de video-shell único | diseño 2 columnas + barra monitorización | Medio |
| `backend/interfaz_usuario_app/app.js` | lógica referencia de selector | algoritmo switch mic | modo write específico | utilidades de selector adaptadas a AV | Medio |

## 10) Riesgos o puntos delicados
- Cambiar dispositivo durante grabación puede cortar continuidad de audio/video; UX debe avisar.
- Añadir waveform requiere cuidado de rendimiento y cleanup de AudioContext.
- Hay que separar claramente “vista previa de ti” vs “guía AIDA”, evitando competir por foco.

## 11) Criterio de aceptación visual/UX
- El usuario graba con guía AIDA visible en todo momento.
- Puede gestionar mic/cámara con UI moderna, sin selects crudos.
- Estado AV (OK/KO) y actividad de audio se perciben de forma inmediata.
- La pantalla transmite monitorización continua sin parpadeos agresivos.
