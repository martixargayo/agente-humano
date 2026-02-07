# Auditoría técnica de producción — Avatar 3D conversacional

## 1) Resumen ejecutivo

- **Arquitectura viable en navegador**: el pipeline (texto/voz → backend → TTS → analyser → HBL → shader de partículas) es implementable y, en su forma actual, está correctamente encadenado.
- **Diseño diferencial válido**: el enfoque `Points + shaders + máscaras elipsoidales` es coherente para un avatar estilizado y control procedural, pero **sacrifica fidelidad anatómica y mantenibilidad** respecto a rig facial tradicional.
- **No hay bloqueadores estructurales**, pero sí **riesgos de robustez cross-browser** (MediaRecorder/MIME, políticas de autoplay, clipboard/pointer/touch) y de performance en sesiones largas de edición (`debugEdit=1`) por recomputación CPU de máscaras.
- **Estado recomendado**: **preproducción avanzada**, no “production-ready” total hasta cerrar compatibilidad y tests de estrés/recovery.

## 2) Viabilidad técnica

### Viabilidad del enfoque particles + shaders

**Fortalezas**
- Coste de animación facial en GPU: gran parte de la deformación ocurre en vertex shader con atributos preempaquetados (`aW0`…`aW3`), minimizando lógica CPU por frame.
- Independencia de rig/skeleton: evita asset pipeline complejo de blendshapes y retargeting.
- Tunable runtime: los pesos HBL y pivotes se recalculan en caliente.

**Trade-offs reales**
- Sin malla/skinning: menor control anatómico fino (labio-diente-lengua/oclusiones complejas).
- Dependencia de point density y alpha blending para “leer” expresión; sensible a tamaño de punto, orden de transparencia y depth settings.
- Aumento de atributos por vértice (posición + UV + rand + 4 paquetes de pesos) implica más ancho de banda GPU.

### Cuellos de botella esperables

- **CPU**: `fillWeightsFromPositions` es O(N) por recompute y hace múltiples elipsoides por punto; durante drag se mitiga con throttle de ~70 ms, pero sigue siendo el hotspot del editor.
- **GPU**: shader vertex con múltiples ramas/operaciones trig/ruido por punto; viable en desktop moderno, más frágil en iGPU móviles.
- **Memoria**: varios `Float32Array` por atributo; aceptable para una cara frontal, pero no gratis en sesiones largas si se recrean recursos (aquí no se observa fuga obvia).

### Escalabilidad temporal (sesiones largas)

- El loop principal está acotado (`delta` cap a 1/20), lo que estabiliza comportamiento tras tab throttling.
- No se observan timers descontrolados ni creación continua de geometrías en runtime normal.
- Riesgo principal de larga sesión: degradación por paths de error de audio/mic no testeados en todos los navegadores y editor de debug intensivo.

## 3) Análisis por subsistemas

### a) Render 3D

- Escena/cámara/lights: setup limpio y mínimo (PerspectiveCamera, 2 directional + ambient).
- OrbitControls con damping correcto.
- Resize bien manejado (camera aspect + renderer size + overlay debug).
- Loop: `requestAnimationFrame`, clamp de delta, update HBL y render.

**Observación**: `renderer.setPixelRatio(window.devicePixelRatio)` sin cap puede castigar GPU en pantallas retina; recomendable cap (p.ej. 1.5–2.0) para estabilidad en portátiles.

### b) Sistema de partículas faciales

- GLB merge + recentrado + filtrado frontal (`z >= 0`) consistente con concepto “cara frontal”.
- Packing de atributos `aW0–aW3`, `aRand` correcto y documentado.
- `DynamicDrawUsage` aplicado a buffers que se recomputan (acierto).

**Riesgo técnico**: filtrado frontal puro por `z` depende del origen/orientación del scan; si cambia asset, puede recortar zonas útiles.

### c) Cálculo de pesos HBL

- `buildTuningSnapshot` evita lecturas globales repetidas dentro del loop por vértice (buena práctica).
- `fillWeightsFromPositions` implementa composición jerárquica (head/torso/neck + eye→iris→pupil + lid/brow + jaw/mouth) de forma coherente.
- `seamWeightsY` separa cabeza/cuello/torso con transición suave controlable.

**Coste**: computacionalmente alto pero predecible. Aceptable para una sola geometría facial; no escalaría bien a múltiples avatares simultáneos sin worker o GPU compute.

### d) Shaders

- Vertex shader: integra micro-movimientos, respiración, gaze/iris, blink/squint, jaw/mouth, rotación de cabeza con pivote.
- Fragment shader: disco suave de puntos, densidad por texture map, debug strict/blend, preservación de iris/pupil.
- Uniforms bien mapeados desde HBL.

**Riesgos**
- Branching en fragment (`uDebugMode`) y varios `discard`: normal en este caso, pero puede impactar fill-rate en móviles.
- `precision highp float` puede degradar compatibilidad/perf en GPUs antiguas de móviles (no bloqueante en desktop moderno).

### e) Human Behavior Layer (HBL)

- Modelo de estados está bien definido (`BOOT/IDLE/LISTENING/THINKING/SPEAKING`) y desacoplado de shader.
- Blink probabilístico con distribución exponencial razonable.
- Micro-sacadas con state machine (`idle/step/hold/settle`) y smoothing capped: diseño sólido.
- Respiración, backchannels de escucha y beat durante speaking: buen realismo macro.

**Estabilidad**
- No se detecta feedback loop inestable: señales se suavizan (`emaHalfLife`, `smoothCapped`, rate clamps).
- Riesgo moderado de “look too busy” si tuning se exagera (no un bug, sí calibración).

## 4) Audio y lipsync

- Decodificación base64 robusta (sanitiza data URI/whitespace/url-safe base64).
- Inserta padding inicial (~60 ms) para evitar ataque cortado al inicio.
- RMS temporal sobre `AnalyserNode.getByteTimeDomainData` correcto para lipsync simple.
- `talkLevel` con umbral (`minRms`), escala, floor speaking y attack/release: comportamiento razonable.

**Comportamiento en fallo/silencio**
- Sin analyser: retorna 0 y resetea `lipsyncLevel` (degrada de forma segura).
- Silencio corto: `silentFrameCount` evita mouth-sticking.

**Limitaciones reales**
- Es un lipsync energético (RMS), no fonémico: robusto generalista pero no precisa consonantes/labiodentales.
- `minRms/scale` requerirán ajuste por voz TTS/idioma/salida de audio.

## 5) Auditoría crítica de `?debugEdit=1`

### Funcionalidad

- Overlay inicializado de forma defensiva y con visibilidad toggle (`E`).
- Picking por proyección a pantalla + radio de handle simple y efectivo.
- Drag sobre plano `z=0` con raycaster (`rayToPlane`) implementado correctamente.
- Recompute en caliente de máscaras durante drag + recompute inmediato al soltar (`drag:final`).
- Export JSON por portapapeles (con fallback a consola).
- Reset por grupos (`eye/iris/lid/brow/mouth/jaw/pivot/seam/all`) funcional.

### Performance y estabilidad

- Existe throttle durante drag (`minInterval` 70 ms), buena decisión.
- Snapshot de estado al iniciar drag evita acumulación de error incremental.
- Desactiva OrbitControls durante drag y restaura al finalizar.

### Edge cases peligrosos

- No hay `touchcancel` handler: en móviles, una cancelación de gesto podría dejar estado de drag inconsistente.
- Si `window.innerWidth/innerHeight` cambian drásticamente durante drag, el picking puede sentirse errático hasta siguiente frame/reflow.
- Copia a clipboard depende de contexto seguro/permisos; fallback existe, pero UX no siempre evidente.

### Veredicto del editor

- **Sí**, es una herramienta válida para iteración real.
- **Sí**, permite calibración sin tocar código fuente (centros/radios/pivotes/seam + export JSON).
- Requiere endurecer manejo touch y test cross-browser antes de usarla como herramienta principal en producción.

## 6) Compatibilidad de navegador

### Dependencias de políticas

- `AudioContext.resume()` y reproducción de audio dependen de gesto de usuario (resuelto al arrancar con botón).
- `getUserMedia` requiere HTTPS/localhost + permiso explícito.
- `navigator.clipboard.writeText` para copy JSON depende de permisos/contexto seguro.

### Qué falla sin interacción

- Autoplay/TTS puede quedar bloqueado hasta click/tap inicial.
- Sin permiso de micrófono: modo TALK no opera (la app cae a estado idle con mensaje).

### Riesgos por navegador

- **Chrome/Edge**: base sólida para WebGL + MediaRecorder webm/opus.
- **Firefox**: generalmente OK, pero variaciones de MediaRecorder MIME y timing de eventos.
- **Safari**: principal riesgo (MediaRecorder más restrictivo/heterogéneo según versión; políticas de audio más estrictas).

### Warnings/errores esperables

- `No se ha encontrado material.map...` si GLB sin textura.
- `Sin señal de analyser` en debug cuando no hay fuente activa.
- Errores STT/TTS backend propagados al UI.

## 7) Riesgos reales priorizados

1. **Compatibilidad MediaRecorder + MIME en Safari/Firefox**.
2. **Dependencia fuerte de tunings RMS (`minRms`, `scale`)** para labios naturales con voces distintas.
3. **Carga GPU en equipos de gama media/baja** por point rendering + shaders dinámicos + transparencias.
4. **Editor debug sin cobertura completa de eventos táctiles extremos**.

## 8) Tests recomendados (manuales + estrés)

### A. Flujo end-to-end
1. Arranque, permiso micrófono, saludo TTS.
   - Esperado: transición `BOOT→IDLE→SPEAKING→LISTENING` sin bloqueo.
2. Turnos TALK repetidos (>=20).
   - Esperado: no fuga de estado, UI y orb consistentes.
3. Modo WRITE alternando con TALK.
   - Esperado: cancelación limpia de grabación al cambiar a WRITE.

### B. Audio/lipsync
1. TTS con voz muy baja y muy alta.
   - Esperado: labios se mueven sin saturar ni quedarse bloqueados.
2. Audio silencioso / casi silencioso.
   - Esperado: cierre de boca estable tras 2 frames de silencio.
3. Fallo intencional de analyser (desconectar source en debug).
   - Esperado: `talkLevel=0`, sin excepciones ni NaN.

### C. Estrés
1. Reproducción TTS larga (>=10 min total acumulado).
   - Esperado: sin degradación severa FPS ni locks de AudioContext.
2. Drag continuo en debug editor durante 2–3 min.
   - Esperado: recompute estable, sin congelamiento, sin pérdida de controles.
3. Cambios rápidos de grupo (1..8..0) + reset/copy repetidos.
   - Esperado: estado consistente y export JSON válido.

### D. Navegadores
- Matriz mínima: Chrome, Edge, Firefox, Safari (macOS + iOS Safari).
- Validar: permisos, grabación, reproducción, copy clipboard, touch drag en editor.

### E. Degradación
1. Sin textura (`material.map` ausente).
   - Esperado: render visible con densidad uniforme.
2. Sin micrófono / permiso denegado.
   - Esperado: mensaje claro, app usable en modo WRITE.
3. Backend caído (`/chat`, `/negociar`, `/tts`, `/stt_google`).
   - Esperado: errores informativos y recuperación a IDLE/LISTENING según modo.

## 9) Conclusión final

El sistema está **bien diseñado a nivel arquitectónico** para su objetivo (avatar conversacional estilizado, procedural, editable en caliente). No detecto anti-patrones graves ni defectos estructurales que invaliden el enfoque.

No obstante, para certificar “producción” con confianza alta faltan:
- Validación robusta multi-navegador (especialmente Safari).
- Batería de estrés formal de audio+editor.
- Ajustes de hardening en interacción táctil/editor y budgets de performance (cap de pixel ratio recomendado).

**Dictamen**: diseño técnicamente sólido y cercano a producción, pero aún en fase de hardening.
