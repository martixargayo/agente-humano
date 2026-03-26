# Plan de implementación: pantalla de entrada AV idéntica (Negociación)

## Objetivo

Construir en la interfaz de negociación una **pantalla inicial visualmente idéntica** a `entryOverlay` (misma estética, espaciados, tipografía, redondez, bordes, sombras, colores, CTA y estado de escenario), pero adaptada a un flujo **100% video**:

- Sin tabs `Hablar / Escribir`.
- Con dos apartados de permisos y selección:
  - **Cámara**
  - **Micrófono**
- Mismo procedimiento de solicitar permisos y habilitar “Empezar” cuando todo esté listo.

---

## Referencia base (no reinventar, clonar)

Tomar como referencia exacta en negociación:

- HTML base de overlay: `backend/interfaz_usuario_app/index.html` (`#entryOverlay`).
- CSS visual `.entry-*`: mismo archivo.
- Máquina de estados y flujo de permisos/dispositivos: `backend/interfaz_usuario_app/app.js`.

La estrategia correcta es **copiar y adaptar**, no reestilizar desde cero.

---

## Alcance funcional del nuevo overlay AV

## Lo que se mantiene igual

1. Capa completa modal (`role="dialog"`, `aria-modal="true"`).
2. Card central con la misma forma, sombras, bordes y jerarquía visual.
3. Subtítulo de guía dinámica.
4. CTA único `Empezar` con estados dinámicos.
5. `entryError` para errores operativos.
6. Estado inferior de escenario (`entryScenarioState` + spinner + texto `Cargando/Escenario cargado`).
7. Transición de salida: clase `.hidden` y `display:none` diferido.

## Lo que cambia

1. Se elimina por completo el switch `Hablar / Escribir`.
2. El contenido central pasa a tener dos secciones permanentes:
   - Sección Cámara.
   - Sección Micrófono.
3. El gating de “Empezar” depende de **ambos** dispositivos (si cámara es obligatoria para el caso de uso).
4. Al pulsar “Empezar”, se precalientan **audio + video** antes de cerrar el overlay.

---

## Plan de cambios por capa

## 1) HTML (estructura)

Partiendo del bloque actual, crear un nuevo layout `entry-av`:

### 1.1 Eliminar tabs

Eliminar:

- `entry-mode-tabs`
- `entryModeTalk`
- `entryModeWrite`
- `entryTalkContent`
- `entryWriteContent`

### 1.2 Mantener card, subtitle, CTA y estado de escenario

Conservar exactamente:

- `entryOverlay`
- `entry-card`, `entry-card-content`
- `entrySubtitle`
- `startBtn`
- `entryError`
- `entryScenarioState`, `entryScenarioSpinner`, `entryLoadingText`

### 1.3 Añadir dos bloques de dispositivos (simétricos)

Dentro de `entry-card-content`, crear:

#### Bloque Cámara

- `entryCameraLabel`
- `entryCameraSearch`
- `entryCameraList` (`role="listbox"`, `aria-label="Seleccionar dispositivo de cámara"`)
- `entryCameraStatus`

#### Bloque Micrófono

- `entryDeviceLabel` (o renombrar a `entryMicLabel` para claridad)
- `entryDeviceSearch` (o `entryMicSearch`)
- `entryDeviceList` (o `entryMicList`)
- `entryDeviceStatus` (o `entryMicStatus`)

> Recomendación de consistencia: usar nombres nuevos `entryMic*` y `entryCamera*` para evitar ambigüedad.

---

## 2) CSS (estética idéntica)

## 2.1 Reutilización estricta del estilo actual

Mantener sin cambios visuales:

- `.entry-overlay`
- `.entry-card`
- `.entry-card-content`
- `.entry-subtitle`
- `.entry-actions`
- `.primary-btn`
- `.error-text`
- `.entry-scenario-state`

## 2.2 Duplicar patrones de lista de audio para cámara

Crear clases de cámara equivalentes a audio:

- `.entry-camera-label` ~ `.entry-device-label`
- `.entry-camera-search` ~ `.entry-device-search`
- `.entry-camera-list` ~ `.entry-device-list`
- `.entry-camera-option` ~ `.entry-device-option`
- `.entry-camera-empty` ~ `.entry-device-empty`
- `.entry-camera-status` ~ `.entry-device-status`

Misma paleta, radios, sombras y tipografía.

## 2.3 Iconografía

- Cámara: icono `📷` o SVG de cámara con estilo equivalente al icono de mic.
- Micrófono: mantener iconografía actual.

## 2.4 Layout interno

- Dos bloques en columna con separación vertical consistente.
- Mantener alturas/overflow para listas igual que en el bloque de audio actual para que la “sensación visual” sea igual.

---

## 3) JS (máquina de estados AV)

## 3.1 Nuevo estado de entrada

Agregar variables de estado:

- `entryCameraPermissionStatus = 'unknown' | 'prompt' | 'granted' | 'denied'`
- `entryMicPermissionStatus = 'unknown' | 'prompt' | 'granted' | 'denied'`
- `availableVideoInputDevices = []`
- `availableAudioInputDevices = []`
- `selectedEntryCameraDeviceId = null`
- `selectedEntryMicDeviceId = null`
- `entryInProgress`, `entryRequested`, `scenarioReady` (reusar).

## 3.2 Referencias UI

En el objeto `ui`, añadir:

- `entryCameraLabel`, `entryCameraSearch`, `entryCameraList`, `entryCameraStatus`
- `entryMicLabel`, `entryMicSearch`, `entryMicList`, `entryMicStatus`

Y eliminar referencias de tabs/modos en este flujo.

## 3.3 Render central único

Crear `renderEntryAvState()` (análogo a `renderEntryState()`), responsable de:

1. Subtítulo contextual.
2. Header búsqueda/permiso de cámara.
3. Header búsqueda/permiso de mic.
4. Textos de estado de cámara/mic (error o ready).
5. Estado spinner de escenario.
6. Estado + texto de botón `startBtn`.

Reglas sugeridas del botón:

- `Cargando escenario…` si `!scenarioReady` y hubo request.
- `Activar cámara y micrófono` si falta alguno de los permisos.
- `Empezar` cuando permisos y selección están completos.

## 3.4 Solicitud de permisos AV

Crear `requestAvPermissionsForEntry()`:

- Ejecutar `getUserMedia({ audio: ..., video: ... })` en una sola acción.
- Si falla con `Overconstrained/NotFound` por deviceId exacto, fallback a constraints base.
- Mapear errores a mensajes claros en `entryError` y estados de `entryCameraStatus` / `entryMicStatus`.

## 3.5 Enumeración de dispositivos

Separar normalizadores:

- `toUiAudioInputDevices(rawDevices)` (reusar patrón actual).
- `toUiVideoInputDevices(rawDevices)` (nuevo, dedupe por `groupId + label`).

Crear `refreshEntryAvDevices()`:

- `enumerateDevices()`
- llenar arrays audio/video según permiso.
- conservar selección previa si existe (`pickReplacementDevice` reutilizable).
- persistir ids en localStorage (`last_audio_input`, `last_video_input`).

## 3.6 Render de listas

- `renderEntryMicDevices()` para mic.
- `renderEntryCameraDevices()` para cámara.

Ambas con el mismo patrón:

- sin permiso -> bloque instructivo;
- sin dispositivos -> empty state;
- con dispositivos -> opciones clicables + `aria-selected`.

## 3.7 Validación previa a entrada

Crear `validateAvEntry()`:

1. si falta permiso -> pedir permisos AV.
2. refrescar dispositivos.
3. comprobar selección de cámara y mic.
4. devolver:
   - `false` si no está listo;
   - `'ready-after-permission'` cuando acaba de concederse;
   - `'ready'` cuando todo estaba ya correcto.

## 3.8 Inicio y cierre

`handleStartEntryAv()`:

- llama `validateAvEntry()`.
- precalienta captura AV (o instancia de recording pipeline).
- setea estado “Listo para grabar”.
- solicita `finalizeEntry()` cuando `scenarioReady` esté true.

`finalizeEntry()`:

- idéntico a referencia: `.hidden` + timeout 240ms -> `display:none`.

## 3.9 Eventos de sincronización

Mantener misma robustez:

- polling periódico mientras overlay visible.
- `mediaDevices.devicechange`.
- `focus`, `pageshow`, `visibilitychange`.
- onchange de permisos (`camera` y `microphone`).

---

## 4) Reglas UX/estéticas para garantizar “idéntica”

1. **No tocar** medidas base de `.entry-card` y `.entry-overlay`.
2. Reusar exactamente radios (`14px`, `26px`, `999px`) y sombras actuales.
3. Misma familia tipográfica (`Inter` + fallback).
4. Misma escala de color y estados `error/ready`.
5. Misma animación de spinner (`entrySpin`) y timing.
6. Mismo copy style: instrucciones cortas, orientadas a acción.

---

## 5) Orden recomendado de implementación (iterativo)

### Fase A — Paridad visual sin lógica

1. Clonar HTML/CSS del overlay.
2. Quitar tabs y meter bloques cámara+mic con clases espejo.
3. Confirmar paridad visual (desktop + mobile).

### Fase B — Lógica de permisos/dispositivos

1. Crear estado AV + `renderEntryAvState()`.
2. Implementar `requestAvPermissionsForEntry()`.
3. Implementar `refreshEntryAvDevices()` + render listas.
4. Conectar `startBtn` a validación AV.

### Fase C — Integración con runtime

1. Espera de `scenarioReady` + estado inferior.
2. Precalentamiento de grabación AV.
3. Cierre de overlay con transición idéntica.

### Fase D — Hardening

1. reconexión de dispositivos en caliente (`devicechange`).
2. recuperación ante errores (`NotReadable`, `NotAllowed`, `NotFound`).
3. persistencia de cámara/mic seleccionados.

---

## 6) Checklist de aceptación

- [ ] La pantalla luce igual a la referencia (mismos bordes, sombras, colores, tipografía, espaciados).
- [ ] No existen tabs de modo.
- [ ] Se muestran dos apartados: cámara y micrófono.
- [ ] El botón guía correctamente: activar permisos / empezar / cargando escenario.
- [ ] No permite entrar hasta cumplir reglas AV + escenario listo.
- [ ] Permite seleccionar explícitamente cámara y mic.
- [ ] Reacciona a cambios de hardware/permisos sin recargar.
- [ ] Al entrar, el overlay se oculta con la misma transición que la referencia.

---

## 7) Riesgos y mitigaciones

1. **Diferencias de prompts entre navegadores** (orden de permisos).
   - Mitigación: una única llamada `getUserMedia({audio,video})` y mensajes específicos por error.
2. **Device IDs efímeros** tras reconexión.
   - Mitigación: `pickReplacementDevice` por `groupId/label` + fallback a primer disponible.
3. **Regresión visual por CSS duplicado inconsistente**.
   - Mitigación: reutilizar clases base existentes y añadir sólo las mínimas variantes `camera-*`.

---

## 8) Entregables técnicos

1. **PR 1 (estructura + estilo)**
   - HTML/CSS del overlay AV idéntico.
2. **PR 2 (lógica AV)**
   - estados, permisos, enumeración, selección y gating de CTA.
3. **PR 3 (integración runtime + robustez)**
   - sincronización con escenario, polling/devicechange, fallbacks de error.

Con este plan, la interfaz de negociación tendrá una pantalla inicial prácticamente clonada de `entryOverlay`, pero especializada para grabación de video con permisos y selección explícita de cámara y micrófono.
