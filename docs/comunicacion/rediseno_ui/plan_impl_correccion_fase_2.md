# Plan de implementación correctiva · Fase 2 (parity real de permisos + recording)

## 1. Objetivo de la fase
- Portar la primera pantalla de permisos de `comunicacion` al patrón real de negociación (adaptado a cámara+mic).
- Reorganizar recording para resolver composición AV, `Gestionar`, `Grabar/Detener`, contador y ondas en layout limpio.

**Cierre esperado de fase:**
- Setup percibido como “pantalla de entrada/permisos” al estilo negociación.
- Recording con recuadro AV unificado y controles coherentes por estado.

## 2. Alcance exacto
### Entra en esta fase
- Adaptación del patrón doc 09 a setup AV.
- Refactor de layout recording (estructura + CSS + estado de botones).
- Limpieza final de textos sobrantes en setup/recording.

### No entra todavía
- Eliminación de transición intermedia `screenUploading` (Fase 3).
- Rework total de feedback final y autoentrega (Fase 3).

## 3. Problemas que esta fase corrige
- Setup actual con estructura de panel clásico, no overlay de entrada.
- Duplicación o torpeza visual en estados micro/cámara separados.
- Botones de grabación poco claros en simultaneidad/estado.
- Ondas de audio no integradas en la composición deseada.

## 4. Archivos que se tocarán
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`
- `docs/comunicacion/rediseno_ui/09-extraccion-exacta-pantalla-permisos-negociacion.md` (anexo de mapping aplicado)
- `docs/comunicacion/rediseno_ui/03-pantalla-de-grabacion-redisenada.md` (alineación con implementación)

## 5. Cambios exactos por archivo

### `backend/comunicacion_app/index.html`
- añadir:
  - bloque setup con estructura tipo entrada (`entry-like`), CTA principal único.
  - recuadro AV unificado en recording con:
    - icono mic,
    - icono cámara,
    - estado ambos,
    - botón `Gestionar` a la derecha.
- modificar:
  - `screenSetup` para dejarlo orientado a permisos + readiness.
  - `screenRecording` para separar claramente:
    1) preview cámara,
    2) recuadro AV + gestionar,
    3) zona `Grabar/Detener` + contador,
    4) ondas debajo de preview.
- mover/refactorizar:
  - mover `#recordingWaveform` debajo del recuadro de cámara.
  - integrar `#recordingIndicator` en barra de control de grabación.
- eliminar:
  - textos sobrantes de setup/recording no esenciales.
  - copy redundante tipo “Grabación guiada…”.
- conservar:
  - IDs funcionales de vídeo, dispositivos, grabación y navegación.

### `backend/comunicacion_app/app.js`
- añadir:
  - función `renderSetupEntryState()` (adaptación de `renderEntryState()` con AV).
  - función `syncRecordingActionVisibility()` para ocultar/mostrar `Grabar`/`Detener` según `state.capture.is_recording`.
- modificar:
  - `syncSetupState()` para CTA dinámico tipo negociación:
    - activar permisos,
    - empezar.
  - `syncButtons()` para reforzar exclusividad visual/funcional entre `startRecordingBtn` y `stopRecordingBtn`.
- mover/refactorizar:
  - centralizar actualización de badges AV y contador en una función de composición de recording.
- eliminar:
  - mensajes redundantes de setup/recording que ya no aportan.
- conservar:
  - pipeline de permisos (`requestCapturePermissions`, `openPreviewStream`, `listCaptureDevices`).

### `backend/comunicacion_app/styles.css`
- añadir:
  - estilos de setup tipo entrada: bloque central, CTA principal prominente, estado compacto.
  - estilos de recuadro AV unificado (`.recording-av-pill` / equivalente).
  - estilos de botón `Gestionar` alineado a la derecha del recuadro.
- modificar:
  - layout de recording para jerarquía: preview → AV status/controls → waveform.
  - espaciado y tamaño de waveform para formato pequeño integrado.
- mover/refactorizar:
  - consolidar reglas dispersas de `.recording-av-status` y `.recording-control-bar`.
- eliminar:
  - reglas que fuerzan separación torpe de badges AV.
- conservar:
  - paleta base y estilos de botones existentes donde no choquen.

### `docs/comunicacion/rediseno_ui/09-extraccion-exacta-pantalla-permisos-negociacion.md`
- añadir:
  - bloque “mapping aplicado en Fase 2” (entry ids/functions origen → setup AV destino).
- modificar:
  - marcar piezas migradas/adaptadas.
- mover/refactorizar:
  - N/A
- eliminar:
  - N/A
- conservar:
  - evidencia exacta original.

### `docs/comunicacion/rediseno_ui/03-pantalla-de-grabacion-redisenada.md`
- añadir:
  - layout final implementado y diferencias cerradas.
- modificar:
  - checkboxes de pendientes a resuelto.
- mover/refactorizar:
  - N/A
- eliminar:
  - N/A
- conservar:
  - especificación previa como baseline.

## 6. Cambios de estilo de esta fase
- Referencia negociación:
  - patrón de entrada limpio de `entryOverlay` y CTA único dinámico.
- Patrones/clases a replicar o adaptar:
  - comportamiento de `renderEntryState()` (texto CTA + estado permisos).
- Correcciones visuales concretas:
  - setup centrado, limpio, sin cabecera histórica.
  - recuadro AV único con iconografía clara.
  - `Gestionar` como acción secundaria lateral.
  - contador integrado al estado de grabación.
  - ondas discretas bajo preview.
- Shell/cards/headers a desaparecer en esta fase:
  - textos sobrantes setup/recording heredados de shell anterior.
- Alineación esperada al cierre:
  - setup y recording ya “huelen” a negociación, aunque loading/report aún quedan para Fase 3.

## 7. Nuevas piezas a introducir
- ids:
  - `#recordingAvUnifiedBox` (si se crea contenedor dedicado).
  - `#recordingManageBtn` (si se separa de `manageAvBtn` actual).
- clases:
  - `.setup-entry-like`, `.recording-av-unified`, `.recording-actions-inline`, `.recording-waveform-compact`.
- funciones:
  - `renderSetupEntryState()`
  - `syncRecordingActionVisibility()`
- handlers/listeners:
  - ajuste de listener de `startRecordingBtn`/`stopRecordingBtn` para visibilidad excluyente.
- estado nuevo:
  - opcional `state.capture.recording_controls_mode` para reflejar UI de controles.

## 8. Piezas reutilizadas desde negociación
- Referencia HTML/CSS de entrada desde `interfaz_usuario_app/index.html` (`#entryOverlay`, CTA único).
- Referencia de lógica de estado desde `interfaz_usuario_app/app.js` (`renderEntryState`, texto dinámico de botón).
- **tipo de reutilización:** adaptación (no copia literal) por necesidad AV.

## 9. Orden interno recomendado de implementación
1. Refactor de `screenSetup` markup.
2. Implementar `renderSetupEntryState()` y cableado con permisos AV.
3. Refactor de markup de `screenRecording` (recuadro AV unificado + controls).
4. Aplicar CSS de composición y limpieza visual.
5. Ajustar lógica de visibilidad `Grabar/Detener` + contador.
6. Validación manual completa Fase 2.

## 10. Invariantes / no romper
- Permisos cámara y micrófono deben seguir funcionales.
- Cambio de dispositivos (`video/audio`) debe seguir operativo.
- Grabación debe generar blob, duración y preview de review.
- Navegación Atrás/Continuar no debe romperse.

## 11. Riesgos específicos
- Técnicos: rotura de vínculos por cambios de IDs/clases.
- UX: sobrecompactar y perder legibilidad.
- Integración: conflicto entre panel de gestión AV y nuevo recuadro unificado.
- Regresión: `stopRecordingBtn` visible cuando no toca (o viceversa).

## 12. Estrategia de fallback
- Fallback aceptable: mantener IDs antiguos con wrappers nuevos para evitar romper JS.
- Puede esperar a fase siguiente: parity tipográfica milimétrica del feedback final.
- No puede salir mal: controles `Grabar/Detener` deben ser inequívocos y consistentes.

## 13. Validaciones / checks manuales
- Setup:
  - CTA cambia entre activar permisos y empezar.
  - cámara+mic listos muestran estado correcto.
- Recording:
  - recuadro AV único visible con mic+cam.
  - botón `Gestionar` a la derecha.
  - `Grabar` desaparece al grabar y aparece `Detener`.
  - contador avanza durante grabación.
  - ondas visibles debajo de preview y en tamaño discreto.
- Review:
  - grabación resultante reproducible.

## 14. Criterio de cierre de fase
La fase se cierra cuando:
1. Primera pantalla de permisos tiene composición equivalente a negociación adaptada a AV.
2. Recording cumple composición unificada solicitada (AV/gestionar/grabar-detener/contador/ondas).
3. No quedan textos redundantes en setup/recording.
