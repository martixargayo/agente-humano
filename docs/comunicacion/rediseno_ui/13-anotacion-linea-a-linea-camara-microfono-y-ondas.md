# Anotación línea a línea — cámara, botón de gestión AV y ondas de audio

## Objetivo
Este documento deja **anotado línea a línea** el código actual que construye:
- el cuadro de cámara (self-view),
- el botón para gestionar cámara/micrófono,
- las ondas de audio en vivo,
- y el panel de dispositivos AV.

> Nota de referencia externa: se intentó consultar `http://dev.inner.box` y `https://dev.inner.box` para usarlo como base visual, pero ambos devolvieron `403 Forbidden` (26 de marzo de 2026). Por eso este documento anota el código local existente.

---

## 1) HTML base (estructura UI)
Fuente: `backend/comunicacion_app/index.html`.

### Fragmento A — preview + ondas + estado AV + botón Gestionar
```html
<div class="recording-preview-stack">
  <div class="video-shell video-shell--recording-side">
    <video id="recordingVideo" class="video-frame video-frame--selfview" autoplay playsinline muted></video>
  </div>
  <div id="recordingWaveform" class="recording-waveform recording-waveform--compact" aria-label="Medidor de audio en vivo"></div>
</div>
<div class="recording-av-control-row">
  <div id="recordingAvUnifiedBox" class="recording-av-unified">
    <div id="recordingMicBadge" class="recording-av-item status-badge--idle"><span class="recording-av-icon" aria-hidden="true">🎤</span><span>Micrófono · --</span></div>
    <div id="recordingCamBadge" class="recording-av-item status-badge--idle"><span class="recording-av-icon" aria-hidden="true">📷</span><span>Cámara · --</span></div>
  </div>
  <button id="manageAvBtn" class="btn btn-secondary" type="button" aria-expanded="false">Gestionar</button>
</div>
```

### Anotación línea a línea
1. `recording-preview-stack`: contenedor vertical de preview y waveform.
2. `video-shell video-shell--recording-side`: caja visual de la cámara lateral.
3. `video#recordingVideo`: preview de la cámara; `autoplay`, `playsinline`, `muted` para reproducción local estable.
4. Cierre del contenedor del video.
5. `div#recordingWaveform`: nodo donde JS inyecta barras de onda en tiempo real.
6. Cierre de `recording-preview-stack`.
7. `recording-av-control-row`: fila con estado AV + acción gestionar.
8. `div#recordingAvUnifiedBox`: caja unificada de estado de micrófono/cámara.
9. `div#recordingMicBadge`: badge de estado del micrófono (inicialmente idle).
10. `div#recordingCamBadge`: badge de estado de la cámara (inicialmente idle).
11. Cierre de la caja unificada.
12. `button#manageAvBtn`: abre/cierra el panel de gestión de dispositivos AV; `aria-expanded` arranca en `false`.
13. Cierre de la fila de control.

### Fragmento B — panel de dispositivos AV
```html
<div id="avDevicePanel" class="av-device-panel hidden">
  <div class="av-device-panel__head">
    <h3>Dispositivos activos</h3>
    <button id="closeAvPanelBtn" class="btn btn-secondary" type="button">Cerrar</button>
  </div>
  <div class="av-device-panel__grid">
    <section class="av-device-group">
      <h4>Cámara</h4>
      <div id="recordingVideoDeviceList" class="av-device-options"></div>
    </section>
    <section class="av-device-group">
      <h4>Micrófono</h4>
      <div id="recordingAudioDeviceList" class="av-device-options"></div>
    </section>
  </div>
</div>
```

### Anotación línea a línea
1. `#avDevicePanel`: panel desplegable de dispositivos; `hidden` lo oculta al inicio.
2. Cabecera del panel.
3. Título del panel.
4. Botón para cerrar panel.
5. Cierre de cabecera.
6. Grid de dos columnas (cámara y micrófono).
7. Grupo de cámara.
8. Título del grupo cámara.
9. Contenedor dinámico para opciones de cámara.
10. Cierre grupo cámara.
11. Grupo de micrófono.
12. Título del grupo micrófono.
13. Contenedor dinámico para opciones de micrófono.
14. Cierre grupo micrófono.
15. Cierre grid.
16. Cierre panel.

---

## 2) CSS (apariencia visual)
Fuente: `backend/comunicacion_app/styles.css`.

### Fragmento A — cuadro de cámara (self-view)
```css
.video-shell--recording-side {
  min-height: 180px;
  border: 1px solid #1f2937;
}

.video-frame--selfview {
  max-height: 220px;
  object-fit: cover;
}
```

**Línea a línea**
1. Selector del contenedor de preview en modo grabación.
2. Altura mínima visible del cuadro.
3. Borde oscuro para delimitar el marco.
4. Cierre de regla.
5. Selector del video self-view.
6. Limita altura máxima del video.
7. `cover` recorta para llenar el marco sin deformar.
8. Cierre de regla.

### Fragmento B — ondas de audio
```css
.recording-waveform {
  min-height: 34px;
  border-radius: 10px;
  border: 1px solid #dbe4f0;
  background: #f8fafc;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  padding: 8px;
}

.recording-waveform--compact {
  min-height: 30px;
  padding: 6px;
  gap: 3px;
}

.recording-waveform__bar {
  flex: 1 1 0;
  height: 100%;
  max-width: 8px;
  border-radius: 999px;
  background: #cbd5e1;
  transform-origin: bottom center;
  transform: scaleY(var(--bar-scale, 0.1));
  transition: transform 120ms linear, background-color 140ms linear;
}

.recording-waveform__bar.active {
  background: #2563eb;
}
```

**Línea a línea**
1. Contenedor general del waveform.
2. Alto mínimo base.
3. Esquinas redondeadas.
4. Borde suave del bloque.
5. Fondo claro.
6. Flex para alinear barras.
7. Barras “apoyadas” abajo para crecer hacia arriba.
8. Espaciado horizontal entre barras.
9. Relleno interno.
10. Cierre de regla.
11. Variante compacta.
12. Alto mínimo menor.
13. Menor padding.
14. Menor separación.
15. Cierre de regla.
16. Cada barra individual.
17. Barra flexible para ocupar ancho disponible.
18. Toma toda la altura del contenedor.
19. Ancho máximo por barra.
20. Forma píldora.
21. Color inactivo.
22. Origen de escalado en la base.
23. Escala vertical controlada por variable CSS `--bar-scale`.
24. Transición suave del movimiento/color.
25. Cierre de regla.
26. Estado activo de una barra.
27. Color azul cuando está “encendida”.
28. Cierre de regla.

### Fragmento C — caja AV + badges + botón gestionar
```css
.recording-av-control-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: stretch;
}

.recording-av-unified {
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  background: #f8fafc;
  padding: 8px;
  display: grid;
  gap: 8px;
}

.recording-av-item {
  border-radius: 10px;
  border: 1px solid #cbd5e1;
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.status-badge--ok { color: #166534; border-color: #86efac; background: #f0fdf4; }
.status-badge--ko { color: #b91c1c; border-color: #fecaca; background: #fef2f2; }
.status-badge--idle { color: #475569; background: #f8fafc; }
```

**Línea a línea**
1. Fila que organiza estado AV y botón Gestionar.
2. Usa CSS Grid.
3. Columna flexible (badges) + columna auto (botón).
4. Separación entre columnas.
5. Estira elementos a la misma altura.
6. Cierre de regla.
7. Caja que agrupa badges mic/cam.
8. Borde contenedor.
9. Radio de esquinas.
10. Fondo de caja.
11. Padding interno.
12. Layout vertical.
13. Gap vertical.
14. Cierre de regla.
15. Badge individual (mic o cam).
16. Esquinas badge.
17. Borde badge.
18. Espaciado interno.
19. Texto pequeño.
20. Texto semibold.
21. Layout horizontal icono + texto.
22. Centra verticalmente.
23. Espacio entre icono y texto.
24. Evita salto de línea.
25. Cierre de regla.
26. Estado OK: verde (texto/borde/fondo).
27. Estado KO: rojo (texto/borde/fondo).
28. Estado IDLE: neutro.

---

## 3) JavaScript (comportamiento)
Fuente: `backend/comunicacion_app/app.js`.

### Fragmento A — actualización de badges mic/cam
```js
function refreshCaptureHealthIndicators() {
  const stream = state.capture.media_stream;
  const audioTrack = stream ? stream.getAudioTracks()[0] : null;
  const videoTrack = stream ? stream.getVideoTracks()[0] : null;
  const micBadge = $('recordingMicBadge');
  const camBadge = $('recordingCamBadge');
  if (micBadge) {
    const micHealth = getTrackHealth(audioTrack);
    micBadge.className = `recording-av-item status-badge--${micHealth}`;
    const micText = micBadge.querySelector('span:last-child');
    if (micText) micText.textContent = micHealth === 'ok' ? 'Micrófono · OK' : 'Micrófono · Sin señal';
  }
  if (camBadge) {
    const camHealth = getTrackHealth(videoTrack);
    camBadge.className = `recording-av-item status-badge--${camHealth}`;
    const camText = camBadge.querySelector('span:last-child');
    if (camText) camText.textContent = camHealth === 'ok' ? 'Cámara · OK' : 'Cámara · Sin señal';
  }
}
```

**Línea a línea**
1. Inicia rutina de estado AV.
2. Lee stream actual.
3. Extrae track de audio (si existe).
4. Extrae track de video (si existe).
5. Obtiene nodo badge mic.
6. Obtiene nodo badge cam.
7. Si existe badge mic, actualiza.
8. Evalúa salud de track mic.
9. Reasigna clase para color/estado (`ok/ko/missing`).
10. Busca texto interno del badge.
11. Escribe texto final para mic.
12. Cierre bloque mic.
13. Si existe badge cam, actualiza.
14. Evalúa salud de track cam.
15. Reasigna clase para color/estado.
16. Busca texto interno del badge.
17. Escribe texto final para cámara.
18. Cierre bloque cam.
19. Cierre función.

### Fragmento B — creación/render de barras de onda
```js
function ensureWaveformBars() {
  const node = $('recordingWaveform');
  if (!node || node.dataset.hydrated === 'true') return;
  node.innerHTML = new Array(WAVEFORM_BAR_COUNT).fill(0).map(() => '<span class="recording-waveform__bar"></span>').join('');
  node.dataset.hydrated = 'true';
}

function renderWaveform(levelRatio) {
  ensureWaveformBars();
  const node = $('recordingWaveform');
  if (!node) return;
  const bars = node.querySelectorAll('.recording-waveform__bar');
  const clamped = Math.max(0, Math.min(1, levelRatio || 0));
  const activeBars = Math.max(1, Math.round(clamped * WAVEFORM_BAR_COUNT));
  bars.forEach((bar, index) => {
    const shouldGlow = index < activeBars;
    bar.style.setProperty('--bar-scale', shouldGlow ? `${0.35 + (index / WAVEFORM_BAR_COUNT) * 0.65}` : '0.16');
    bar.classList.toggle('active', shouldGlow);
  });
}
```

**Línea a línea**
1. Función para hidratar barras una sola vez.
2. Busca contenedor waveform.
3. Sale si no existe o ya estaba hidratado.
4. Inyecta `WAVEFORM_BAR_COUNT` spans de barras.
5. Marca nodo como hidratado.
6. Cierra función.
7. Función que pinta amplitud actual.
8. Asegura que barras existan.
9. Reobtiene nodo waveform.
10. Sale si no existe.
11. Obtiene todas las barras.
12. Limita nivel entre 0 y 1.
13. Calcula cuántas barras se activan.
14. Itera barra por barra.
15. Decide si la barra va activa.
16. Ajusta escala vertical con variable CSS.
17. Agrega/quita clase `active`.
18. Cierra iteración.
19. Cierra función.

### Fragmento C — medición de audio con Web Audio API
```js
function startAudioMonitoring(stream) {
  stopAudioMonitoring();
  if (!stream) return;
  try {
    const AudioCtx = global.AudioContext || global.webkitAudioContext;
    if (!AudioCtx) return;
    const audioTrack = stream.getAudioTracks()[0];
    if (!audioTrack) return;
    const context = new AudioCtx();
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.75;
    const source = context.createMediaStreamSource(stream);
    source.connect(analyser);
    state.capture.audio_context = context;
    state.capture.audio_analyser = analyser;
    state.capture.audio_source_node = source;
    state.capture.audio_data_array = new Uint8Array(analyser.fftSize);

    const loop = () => {
      if (!state.capture.audio_analyser || !state.capture.audio_data_array) return;
      state.capture.audio_analyser.getByteTimeDomainData(state.capture.audio_data_array);
      let sumSquares = 0;
      for (let i = 0; i < state.capture.audio_data_array.length; i += 1) {
        const centered = (state.capture.audio_data_array[i] - 128) / 128;
        sumSquares += centered * centered;
      }
      const rms = Math.sqrt(sumSquares / state.capture.audio_data_array.length);
      state.capture.audio_level_ratio = Math.min(1, rms * 3.2);
      renderWaveform(state.capture.audio_level_ratio);
      state.capture.audio_raf_id = global.requestAnimationFrame(loop);
    };
    loop();
  } catch (_error) {
    // noop: monitor visual es best-effort
  }
}
```

**Línea a línea**
1. Arranca monitor de audio.
2. Limpia monitor previo.
3. Sale si no hay stream.
4. Bloque de protección runtime.
5. Detecta `AudioContext` estándar o legacy.
6. Sale si navegador no soporta API.
7. Toma el primer track de audio.
8. Sale si no existe track.
9. Crea contexto de audio.
10. Crea analizador FFT.
11. Define resolución FFT.
12. Suavizado temporal del analizador.
13. Crea fuente desde `MediaStream`.
14. Conecta fuente con analizador.
15. Guarda contexto en estado.
16. Guarda analyser en estado.
17. Guarda source node en estado.
18. Reserva buffer numérico para muestras.
19. Define loop de medición.
20. Sale si faltan referencias runtime.
21. Lee muestras temporales (onda).
22. Inicializa acumulador RMS.
23. Itera muestras.
24. Centra muestra respecto a 0.
25. Acumula potencia.
26. Cierra bucle.
27. Calcula RMS.
28. Mapea RMS a ratio [0,1].
29. Renderiza waveform con ratio.
30. Agenda siguiente frame.
31. Cierre loop.
32. Ejecuta loop inicial.
33. Captura errores silenciosamente (best-effort).
34. Cierre función.

### Fragmento D — botón “Activar cámara y micrófono” + botón “Gestionar”
```js
setupPrimaryBtn.textContent = isSetupReady() ? 'Empezar' : 'Activar cámara y micrófono';

$('setupPrimaryBtn').addEventListener('click', async () => {
  clearError();
  if (isSetupReady()) {
    transitionTo(SCREEN_AIDA_PREP);
    return;
  }
  setBusy(true);
  try {
    const stream = await requestCapturePermissions();
    stopPreviewStream();
    state.capture.media_stream = stream;
    state.capture.stream_active = true;
    await listCaptureDevices();
    await openPreviewStream({
      videoDeviceId: $('videoDeviceSelect').value || state.capture.selected_video_device_id || null,
      audioDeviceId: $('audioDeviceSelect').value || state.capture.selected_audio_device_id || null,
    });
  } catch (error) {
    state.capture.permission_camera = 'denied';
    state.capture.permission_mic = 'denied';
    setError(`No se pudieron conceder permisos: ${error.message}`);
  } finally {
    setBusy(false);
  }
});

$('manageAvBtn').addEventListener('click', () => {
  state.capture.av_panel_open = !state.capture.av_panel_open;
  renderApp();
});
```

**Línea a línea**
1. Cambia texto del botón primario según estado de permisos/listo.
2. Registra click del botón principal de setup.
3. Limpia error previo.
4. Si ya está listo…
5. …navega a pantalla AIDA.
6. Sale del handler.
7. Marca UI como ocupada.
8. Inicia bloque `try`.
9. Pide permisos de captura.
10. Detiene stream previo si existía.
11. Guarda stream en estado.
12. Marca captura activa.
13. Lista dispositivos disponibles.
14. Abre preview con IDs seleccionados.
15. Envía videoDeviceId efectivo.
16. Envía audioDeviceId efectivo.
17. Cierra objeto de configuración.
18. Cierra `await openPreviewStream`.
19. Si falla permiso/captura…
20. Marca permiso cámara denegado.
21. Marca permiso mic denegado.
22. Publica mensaje de error.
23. Bloque final siempre ejecutado.
24. Libera estado busy.
25. Cierre handler setup.
26. Registra click en botón Gestionar.
27. Invierte estado abierto/cerrado del panel AV.
28. Re-renderiza para aplicar visibilidad.
29. Cierre handler Gestionar.

---

## 4) Mapa rápido: qué tocar cuando se quiera llevar a estilo minimalista “tipo OpenAI”
Sin cambiar nada aún, estos son los puntos donde está encapsulado el look & feel:

- **Estructura del bloque visual**: `index.html` (`recording-preview-stack`, `recording-av-control-row`, `avDevicePanel`).
- **Look del cuadro de cámara**: `styles.css` (`.video-shell--recording-side`, `.video-frame--selfview`).
- **Look de ondas**: `styles.css` (`.recording-waveform*`) + `app.js` (`ensureWaveformBars`, `renderWaveform`, `startAudioMonitoring`).
- **Look de badges y estados**: `styles.css` (`.recording-av-item`, `.status-badge--*`) + `app.js` (`refreshCaptureHealthIndicators`).
- **Interacción botón Gestionar / panel**: `app.js` (`manageAvBtn` listener + `renderApp` con `aria-expanded` y clase `hidden`).

Con esto tienes un documento de consulta directa para rediseñar luego sin tocar aún el comportamiento.
