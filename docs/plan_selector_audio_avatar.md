# 1. Objetivo del cambio

Diseñar la incorporación de un **selector robusto de dispositivos de audio** dentro de la interfaz del escenario con avatar, concretamente en la franja superior de la caja inferior (`.bar-inner`, a la misma altura visual que el selector `Hablar / Escribir`, pero alineado a la derecha), para que el usuario pueda:

- ver qué micrófono está seleccionado en ese momento;
- abrir un desplegable limpio y consistente con la UI actual;
- refrescar la lista de dispositivos mientras el desplegable permanece abierto;
- cambiar de micrófono incluso con la conversación ya iniciada;
- hacerlo sin romper el flujo de permisos, grabación, transcripción, reinicio del stream ni la sincronización visual de la bola azul.

La recomendación principal, basada en el código real del repo, es que el primer alcance sea **solo selección de micrófono (`audioinput`)** y **no salida de audio**. La razón técnica es que el frontend actual solo opera de forma explícita sobre `getUserMedia`, `MediaRecorder`, `MediaStreamSource` y el stream de captura de entrada. No existe en este flujo un sistema estable para redirigir la salida TTS a un `audiooutput`, y además el soporte real de `setSinkId` es parcial, exige más superficie UX y abriría una segunda línea de riesgo que no aporta valor inmediato al problema principal.

# 2. Estado actual del sistema implicado

## UI del escenario con avatar

La interfaz activa del escenario está en `backend/interfaz_usuario_app/index.html` y el comportamiento en `backend/interfaz_usuario_app/app.js`.

La barra inferior actual está estructurada así:

- `.bottom-bar` fija la caja inferior flotante.
- `.bar-inner` contiene toda la superficie blanca.
- `.bar-top` contiene hoy el bloque izquierdo `Hablar / Escribir` y, en el HTML actual, un selector `conversationMode` a la derecha.
- `#talkMode` contiene la bola azul (`#inputOrb`), el texto de estado y el botón `Finalizar`.
- `#writeMode` contiene el textarea y el botón `Enviar`.

Importante: aunque `conversationMode` sigue presente en el HTML, el JS lo elimina explícitamente en runtime con `$('conversationMode')?.remove();`. Eso deja la parte derecha de `.bar-top` libre visualmente y lo convierte en el hueco natural para el nuevo selector de audio.

## Selector de dispositivos ya existente, pero solo en entry overlay

El repo ya tiene una base funcional de selección de micrófonos antes de entrar al escenario:

- `#entryOverlay` muestra un diálogo inicial.
- En `#entryTalkContent` ya existen `#entryDeviceSearch`, `#entryDeviceList` y `#entryDeviceStatus`.
- El código ya enumera micrófonos con `navigator.mediaDevices.enumerateDevices()`.
- El sistema ya guarda el último `deviceId` en localStorage.
- El sistema ya intenta reemplazar automáticamente un dispositivo desaparecido usando `groupId` y coincidencia por label normalizada.
- Ya existe polling y escucha de `devicechange` mientras el overlay está visible.

Eso significa que el problema no es “inventar” gestión de dispositivos desde cero, sino **reutilizar y endurecer** la lógica existente para una segunda superficie: el selector en el escenario principal.

## Estado actual del pipeline de audio

El flujo actual relevante es:

1. Se comprueba o pide permiso de micrófono.
2. Se enumeran dispositivos y se selecciona `selectedEntryDeviceId`.
3. Al entrar en modo hablar o volver a hablar, `startVoiceCapture()` hace `teardownMic()`, pide `getUserMedia()` con `deviceId` si existe, crea `MediaRecorder`, y además crea `AnalyserNode` + `MediaStreamSource` para alimentar la bola azul.
4. Al finalizar turno, `stopVoiceCapture()` detiene `MediaRecorder`, genera un `Blob`, se transcribe, se obtiene respuesta, se reproduce TTS y luego se vuelve a levantar captura si el modo sigue siendo `Hablar`.

## Diferencia importante entre “avatar” y “bola azul”

En este frontend conviven dos representaciones de audio distintas:

- **La bola azul de escucha** (`#inputOrb`) depende del `waveAnalyser` creado a partir del micrófono en `startVoiceCapture()`. Es el riesgo principal al cambiar de micro en caliente.
- **La animación de boca/habla del avatar** en `avatar_runtime/runtime.js` usa `runtime.connectAnalyser(analyser)` durante reproducción TTS. No está conectada al micrófono de entrada actual. Por tanto, el selector de micro no debería romper directamente la boca del avatar cuando este habla, pero sí puede romper la experiencia de escucha y el reinicio del siguiente turno si no se reinicia bien el stream.

# 3. Archivos y componentes afectados

## Archivos del flujo actual identificados

### UI / layout principal
- `backend/interfaz_usuario_app/index.html`
  - Define `.bottom-bar`, `.bar-inner`, `.bar-top`, `.mode-tabs`, `#talkMode`, `#writeMode`, `#finishTurnBtn`.
  - Es el lugar correcto para insertar el nuevo bloque visual a la derecha de `.bar-top`.

### Lógica principal de interfaz y audio
- `backend/interfaz_usuario_app/app.js`
  - Gestiona modos `Hablar / Escribir`.
  - Gestiona permisos de micrófono.
  - Gestiona enumeración de dispositivos.
  - Gestiona persistencia de `deviceId`.
  - Gestiona `getUserMedia`, `MediaRecorder`, `AnalyserNode`, `MediaStreamSource`, parada y reinicio de captura.
  - Es el archivo central donde habrá que separar más claramente:
    - estado visual del selector en escenario;
    - estado de dispositivos disponibles;
    - estado del pipeline activo;
    - aplicación diferida o inmediata del cambio de micro.

### Runtime del avatar
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`
  - No necesita cambios grandes para el selector visual.
  - Solo hay que tenerlo en cuenta por la relación indirecta con `syncAvatarMode()` y con el hecho de que el avatar no usa el micro para mover la boca, sino el analyser del TTS.

## Componentes visuales nuevos que haría falta crear cuando se implemente

### En HTML
En `.bar-top`, a la derecha:
- trigger del selector, p. ej. `#audioDeviceSelector`
- botón principal, p. ej. `#audioDeviceTrigger`
- icono de auriculares en negro
- label con nombre del dispositivo activo
- chevron a la derecha
- popover ascendente, p. ej. `#audioDevicePopover`
- contenedor de opción seleccionada arriba
- contenedor del resto de opciones debajo
- footer fijo con “Buscando dispositivos…” + spinner

### En CSS
Nuevos bloques de estilo para:
- trigger compacto tipo píldora / chip interactivo
- popover ascendente con sombra clara y borde suave
- variante responsive
- estado abierto / cerrado
- opción activa / hover / disabled
- spinner y footer de refresh
- truncado robusto de labels largos

### En JS
Nuevos grupos de estado para:
- apertura/cierre del popover
- polling específico del popover
- estado de “refreshing”
- estado de aplicación de cambio de dispositivo
- estrategia de reinicio controlado del pipeline
- notificación visual de error o fallback cuando falle un cambio en caliente

# 4. Diseño visual propuesto

## Posición exacta
El selector debe ir en `backend/interfaz_usuario_app/index.html`, dentro de `.bar-top`, alineado a la derecha, ocupando el hueco que hoy deja libre el `conversationMode` eliminado por JS.

Estructura visual propuesta dentro de `.bar-top`:

- izquierda: `Hablar / Escribir`
- derecha: selector de audio

No debe ir en `#talkMode`, porque ahí competiría visualmente con la bola azul y el botón `Finalizar`, y además el usuario ha pedido explícitamente que comparta altura con `Hablar / Escribir`.

## Apariencia del trigger

Diseño recomendado:

- contenedor horizontal, altura aproximada 34–40 px;
- fondo blanco o gris muy claro, coherente con `html[data-newbox="1"]`;
- borde suave parecido al de `.finish-button` y `.mode-tabs`;
- icono negro de auriculares a la izquierda;
- texto del dispositivo seleccionado en el centro/izquierda;
- flecha negra o gris oscuro hacia abajo a la derecha;
- comportamiento de botón completo: al pulsar cualquier zona se abre/cierra.

## Apariencia del desplegable

El usuario ha pedido expresamente que **se abra hacia arriba** para no tapar el botón `Finalizar` ni `Enviar`. Por eso la recomendación es usar un **popover anclado al trigger con `bottom: calc(100% + 10px)`**, no un dropdown tradicional hacia abajo.

Contenido del popover:

1. **Bloque superior fijo o primera opción destacada** con el micrófono seleccionado.
2. **Bloque inferior** con el resto de dispositivos disponibles.
3. **Footer persistente** con:
   - texto `Buscando dispositivos…`
   - spinner a la derecha

Aspecto visual:

- ancho aproximado 280–340 px;
- fondo blanco;
- borde `rgba(15, 23, 42, 0.10)`;
- sombra suave similar a `.bar-inner`;
- radius 16–18 px;
- cada opción con padding 10–12 px;
- selected con fondo azul muy suave o gris ligeramente resaltado;
- labels con truncado pero accesibles vía `title`.

## Responsive

Para no romper layout actual:

- en escritorio, `.bar-top` puede seguir en una fila con `justify-content: space-between`;
- en anchos pequeños, el selector debe poder encogerse y truncar el nombre del dispositivo;
- si el ancho es muy estrecho, puede pasar a una segunda línea dentro de `.bar-top`, pero siempre arriba de `#talkMode` / `#writeMode`;
- el popover debe seguir abriéndose hacia arriba y preferiblemente alineado al borde derecho de `.bar-inner`.

# 5. Diseño de interacción UX

## Apertura y cierre

Comportamiento recomendado:

- click en icono, nombre o flecha => abre/cierra, porque todo el trigger es un botón único;
- click fuera => cierra;
- tecla `Escape` => cierra;
- al seleccionar dispositivo => cierra, salvo que se quiera mostrar un estado de “aplicando cambio” dentro del mismo trigger; la recomendación es cerrar tras selección y reflejar estado en el trigger;
- si el usuario reabre el selector más tarde => se dispara un refresh inmediato.

## Orden visual de la lista

El popover debe mostrar:

1. dispositivo seleccionado arriba;
2. separador opcional sutil;
3. resto de dispositivos debajo.

Esto no es solo cosmético: ayuda a evitar que el usuario pierda contexto cuando hay varios micros parecidos.

## Labels vacíos

El repo ya normaliza labels vacíos con `Micrófono N`. Esa misma regla debe reutilizarse en el selector del escenario para evitar divergencias entre el overlay inicial y el selector nuevo.

## Estado sin permisos

Mientras no haya permiso:

- trigger visible, pero con texto tipo `Micrófono no disponible` o `Activar micrófono`;
- popover con explicación corta: `Necesitamos permiso para listar los micrófonos disponibles`;
- si el usuario pulsa seleccionar sin permiso, la fase 1 del plan debería limitarse a informar y llevar el flujo a la CTA de activación ya existente, no a duplicar prompts agresivos desde el selector.

## Estado sin dispositivos

Si hay permiso pero no hay `audioinput` válido:

- trigger visible pero en estado desactivado o warning suave;
- popover con opción no interactiva: `No hay dispositivos de entrada disponibles`.

## Footer “Buscando dispositivos…”

El footer debe estar siempre visible mientras el popover está abierto, no solo cuando haya petición en vuelo. El objetivo es comunicar que la lista se mantiene viva.

Para evitar sensación de bug, conviene diferenciar dos cosas:

- **estado visual permanente**: texto + spinner leve;
- **refresh real en vuelo**: un `data-refreshing=true` o clase que acelere/spainee más claramente o muestre una opacidad distinta.

# 6. Estados del componente

Estados visuales/funcionales recomendados:

1. `closed_idle`
   - trigger cerrado
   - muestra dispositivo seleccionado o estado vacío

2. `open_refreshing`
   - popover abierto
   - polling activo
   - footer visible

3. `open_no_permission`
   - popover abierto
   - lista no disponible por permiso
   - mensaje explicativo

4. `open_empty`
   - popover abierto
   - no hay dispositivos

5. `switch_pending`
   - el usuario ha elegido otro dispositivo
   - el sistema está aplicando el cambio o marcándolo para reinicio controlado

6. `switch_failed`
   - el intento de cambio falló
   - se conserva o restaura el dispositivo anterior
   - se comunica error no destructivo

7. `device_missing_fallback`
   - el dispositivo persistido o seleccionado desapareció
   - se eligió reemplazo por heurística o se quedó en estado sin dispositivo

8. `recording_locked_transition`
   - conversación en modo hablar y captura activa
   - el cambio requiere transición controlada del pipeline

# 7. Flujo técnico actual del audio relevante

## Permisos

- `syncMicPermissionState()` usa `navigator.permissions.query({ name: 'microphone' })` cuando está disponible.
- `requestMicPermissionsForEntry()` hace un `getUserMedia()` real para disparar permiso y valida además si el dispositivo preferido funciona.
- Si hay errores recuperables (`NotReadableError`, `NotFoundError`, `OverconstrainedError`) y existía `selectedEntryDeviceId`, intenta fallback sin `deviceId` exacto.

## Enumeración y persistencia

- `refreshEntryDevices()` hace `enumerateDevices()`.
- `toUiAudioInputDevices()` filtra `audioinput`, deduplica por `groupId + label normalizado` y ordena por nombre.
- `pickReplacementDevice()` intenta mantener continuidad usando:
  - `deviceId` exacto;
  - `groupId`;
  - label normalizado;
  - primer dispositivo disponible como fallback.
- `saveEntryDeviceId()` guarda `interfaz_usuario:last_audio_input_device` en localStorage.

## Captura y grabación

- `startVoiceCapture()` hace `teardownMic()` antes de empezar siempre.
- Luego solicita stream con `selectedEntryDeviceId` si existe.
- Si ese `deviceId` falla con `NotFoundError` o `OverconstrainedError`, reintenta sin `deviceId` y refresca lista.
- Crea `MediaRecorder` y arranca chunks cada 250 ms.

## Bola azul / análisis de señal

- Tras crear stream, `startVoiceCapture()` crea `waveAnalyser = waveAudioCtx.createAnalyser()`.
- Crea `waveSourceNode = waveAudioCtx.createMediaStreamSource(micStream)`.
- `updateInputOrb()` consume `waveAnalyser.getByteTimeDomainData(waveDataArray)` para mover la bola.

## Parada y reinicio entre turnos

- `handleFinishTurn()` detiene la captura, transcribe, llama backend, reproduce TTS y después vuelve a hacer `startVoiceCapture()` si el modo sigue siendo hablar.
- Eso significa que ya existe un patrón de “parar pipeline, procesar, volver a levantar pipeline”, pero ahora está orientado a fin de turno, no a cambio de micro en caliente.

# 8. Flujo técnico propuesto tras añadir el selector

## Idea central

No conviene acoplar directamente “click en opción” con “reconstrucción inmediata y ciega de todo”. La implementación segura debe separar:

1. **selección visual / intención del usuario**;
2. **aplicación técnica del nuevo dispositivo**;
3. **reinicio controlado del pipeline si el mic está activo**.

## Nueva capa lógica recomendada

Introducir una abstracción ligera tipo:

- `audioDeviceUiState`
- `audioCaptureState`
- `pendingDeviceSwitch`

Con ello, el selector no hablaría directamente con `MediaRecorder`; hablaría con una función central, por ejemplo `requestAudioInputDeviceSwitch(deviceId, source)`.

## Flujo propuesto de cambio

### Caso A: el micrófono no está activo en ese momento
Ejemplos:
- usuario en modo escribir;
- usuario en modo hablar pero sin grabación levantada todavía.

Entonces el cambio puede ser casi inmediato:

1. actualizar `selectedEntryDeviceId`;
2. persistir en localStorage;
3. refrescar UI del trigger/popover;
4. no tocar stream porque no existe;
5. el siguiente `startVoiceCapture()` ya usará el nuevo `deviceId`.

### Caso B: el micrófono está activo y se está grabando
Este es el caso delicado.

Flujo recomendado:

1. el usuario selecciona otro micro;
2. se marca el selector como `switch_pending`;
3. se ejecuta una transición controlada:
   - detener `MediaRecorder` de forma segura;
   - descartar chunks parciales si el cambio no debe enviar ese audio como turno;
   - detener tracks del stream actual;
   - desmontar analyser/source/orb loop asociado al stream anterior;
   - reconstruir stream con nuevo `deviceId`;
   - recrear `MediaRecorder`;
   - recrear analyser/source;
   - reactivar captura si el modo sigue siendo hablar;
   - devolver estado a `Escuchando…`.

## Recomendación sobre la conversación activa

La recomendación más segura es:

- **no enviar automáticamente un fin de turno** al cambiar de micro;
- tratar el cambio como una **reconfiguración de captura**, no como parte semántica de la conversación;
- cualquier audio parcial capturado en ese instante debe descartarse para no mezclar fragmentos de dos micrófonos en un mismo blob.

Eso implica que el cambio puede causar una microinterrupción del estado “escuchando”, pero debe terminar en un nuevo estado estable y limpio.

# 9. Estrategia de refresco de dispositivos

## Qué ya existe

Ahora mismo existe:

- polling cada 3 s vía `startEntryDevicePolling()`;
- `devicechange` listener;
- refresh en `focus`, `pageshow` y `visibilitychange`;
- pero todo esto está condicionado a que `#entryOverlay` siga visible.

## Qué conviene hacer para el nuevo selector

Crear una estrategia específica para el escenario principal, separada del overlay de entrada.

### Recomendación

Mientras el popover esté abierto:

- refresh inmediato al abrir;
- activar polling ligero cada `2000–3000 ms`;
- mantener también el listener `devicechange` existente, pero sin duplicar renders innecesarios;
- parar polling al cerrar.

## Cómo evitar parpadeos

Para evitar que la lista “salte” visualmente en cada refresh:

- mantener reconciliación DOM por `deviceId`, igual que ya se hace en el overlay;
- no vaciar la lista entera si el refresh sigue devolviendo elementos parecidos;
- reordenar solo si cambia realmente el seleccionado o aparecen/desaparecen devices;
- mantener el seleccionado arriba mediante una lista derivada para UI, sin reescribir todo el estado base más de lo necesario.

## Footer de búsqueda

El footer `Buscando dispositivos…` debe seguir visible aunque no haya una petición exacta en vuelo; el polling simplemente alimenta ese estado continuo.

# 10. Estrategia de cambio de dispositivo en caliente

## Principio de seguridad

El mayor riesgo del cambio de micro en caliente no es la lista visual, sino dejar referencias colgantes a:

- `micStream`
- `mediaRecorder`
- `audioChunks`
- `waveAnalyser`
- `waveSourceNode`
- `waveDataArray`
- `orbRaf`

Hoy ese desmontaje está repartido entre `teardownMic()`, `stopVoiceCapture()` y los flujos de `setInputMode()` / `handleFinishTurn()`. Para soportar cambio en caliente de forma seria, conviene introducir un **reinicio controlado del pipeline de captura**, explícito y reutilizable.

## Reinicio controlado recomendado

Crear conceptualmente una rutina tipo `restartVoiceCaptureForDeviceChange()` que:

1. capture snapshot del estado actual:
   - modo actual;
   - si había grabación activa;
   - si hay turno de voz en curso;
   - deviceId actual y nuevo;
2. bloquee nuevas acciones concurrentes temporalmente;
3. si hay grabación activa:
   - detenga recorder sin enviar turno;
   - marque descarte de chunks;
4. haga `teardownMic()` completo;
5. intente arrancar `startVoiceCapture()` con el nuevo device;
6. si falla:
   - intente fallback seguro sin `deviceId` exacto o con un replacement válido;
   - restaure estado visual informando al usuario;
7. si tiene éxito:
   - actualice UI y texto de estado a `Escuchando…`;
   - restablezca la bola azul porque el nuevo `waveAnalyser` ya estará conectado.

## ¿Aplicación instantánea o diferida?

### Recomendación
- si **no** hay captura activa: instantánea;
- si **sí** hay captura activa pero **no** hay fin de turno en curso: instantánea con reinicio controlado;
- si hay `voiceTurnInFlight` o `turnInFlight`: **diferir** y bloquear el selector temporalmente o mostrar `Cambio disponible al terminar este turno`.

Razón: durante `handleFinishTurn()` ya se está deteniendo, transcribiendo y rearmando el pipeline. Intervenir ahí con otro cambio puede romper blobs, dejar dobles `startVoiceCapture()` o desincronizar el estado de botones.

## Qué hacer con `MediaRecorder`

`MediaRecorder` debe reiniciarse; no es seguro intentar reutilizarlo con otro stream.

## Qué hacer con `AudioContext` y analyser

No hace falta recrear el `AudioContext` global, pero sí:

- crear nuevo `MediaStreamSource` para el nuevo stream;
- crear o resetear `AnalyserNode` asociado a ese stream;
- regenerar `waveDataArray`.

## Bola azul

La bola azul quedará protegida si el reinicio siempre pasa por la misma ruta que hoy usa `startVoiceCapture()`: crear analyser nuevo y luego `ensureOrbLoop()`.

# 11. Riesgos técnicos

## Riesgo 1: condiciones de carrera entre cambio de micro y fin de turno

Es el riesgo más alto.

Casos peligrosos:
- usuario pulsa `Finalizar` justo cuando cambia de dispositivo;
- `handleFinishTurn()` detiene recorder mientras el selector intenta reiniciarlo;
- `startVoiceCapture()` se llama dos veces seguidas desde rutas distintas.

Mitigación:
- introducir bandera de transición de dispositivo, p. ej. `deviceSwitchInFlight`;
- deshabilitar temporalmente trigger y/o botón `Finalizar` durante la transición;
- no permitir cambio si `voiceTurnInFlight` o `turnInFlight` ya están activos.

## Riesgo 2: dejar la bola azul sin señal

Si se cambia `selectedEntryDeviceId` pero no se rehace correctamente `waveSourceNode` y `waveAnalyser`, la UI puede parecer “escuchando” pero la bola azul quedarse muerta.

Mitigación:
- centralizar el reinicio pasando siempre por `startVoiceCapture()` o una función compartida que recree exactamente analyser/source.

## Riesgo 3: `NotReadableError` o dispositivo ocupado

El nuevo micro puede existir pero estar ocupado por otra app.

Mitigación:
- al fallar el switch, revertir al dispositivo anterior si sigue disponible;
- mostrar error no destructivo;
- no dejar el modo hablar en un estado falso de escucha.

## Riesgo 4: divergencia entre overlay inicial y selector principal

Si se duplica lógica, el overlay puede mostrar una lista y el selector otra.

Mitigación:
- factorizar las funciones comunes de device list / selección / heurística de replacement;
- usar el mismo estado base para ambas superficies.

## Riesgo 5: persistencia inválida entre sesiones

`deviceId` puede cambiar entre reinicios del navegador o incluso entre permisos.

Mitigación:
- validar el valor persistido en cada refresh;
- si no existe, usar `pickReplacementDevice()`;
- si no hay replacement, dejar estado vacío y no forzar un `exact` inválido.

# 12. Casos límite y comportamiento esperado

## Usuario entra sin permisos
- El selector del escenario puede mostrarse, pero debe estar en estado informativo.
- No debe prometer lista real hasta que haya permiso.
- Si abre el popover, debe ver mensaje de permiso y no una lista vacía engañosa.

## Usuario concede permisos y aparecen dispositivos
- El sistema refresca lista.
- Se selecciona el guardado o el primer replacement válido.
- El trigger actualiza el nombre del micrófono sin recargar la página.

## Usuario deniega permisos
- El selector mantiene mensaje de bloqueo.
- Debe seguir siendo posible usar modo `Escribir`.

## Usuario conecta auriculares nuevos con el desplegable abierto
- El polling o `devicechange` debe incorporar el nuevo dispositivo en pocos segundos sin cerrar el popover.
- Si el nuevo dispositivo coincide por label/group con el actual, no debe saltar el seleccionado automáticamente salvo desconexión del activo.

## Usuario desconecta el micro seleccionado
- En el siguiente refresh, si el micro desaparece y no estaba capturando, se aplica replacement automático.
- Si estaba capturando, el cambio debe detectarse y forzar reinicio/fallback o mostrar error claro, evitando estado zombi.

## Usuario cambia a otro micro mientras la conversación está activa
- Si solo está en modo hablar y escuchando, se hace reinicio controlado.
- Si ya se está procesando un turno, el cambio se difiere o se bloquea temporalmente.

## Usuario vuelve a abrir el menú más tarde y quiere refrescar
- Abrir el popover debe lanzar refresh inmediato.
- Mantenerlo abierto debe seguir buscando nuevos dispositivos.

## El `deviceId` almacenado ya no existe
- Se intenta replacement por `groupId` o label.
- Si no hay replacement, se selecciona el primero disponible.
- Si no hay ninguno, se informa visualmente.

## Hay dos dispositivos con labels parecidos
- Mantener `title` completo en opciones.
- Si se quiere endurecer en fase posterior, añadir subtítulo opcional con fragmento de group info solo si hay colisión visible.

## `NotReadableError` al cambiar de micro
- No dejar el selector mintiendo sobre el nuevo micro como “activo” si no pudo levantarse la captura.
- Revertir a dispositivo anterior o a fallback estable.
- Mostrar mensaje: el dispositivo está ocupado o no pudo activarse.

# 13. Propuesta de implementación por fases

## Fase 0 — Refactor previo mínimo de diseño lógico
Sin tocar todavía comportamiento visible final, preparar internamente:

- separar estado de dispositivos del overlay de entrada y del escenario;
- crear helpers compartidos para lista derivada (seleccionado primero / resto después);
- introducir flags de transición de cambio de dispositivo.

## Fase 1 — Implementación visual del selector en escenario
- añadir HTML del trigger y popover en `.bar-top`;
- añadir CSS del trigger, popover ascendente, lista, footer con spinner;
- conectar apertura/cierre, click fuera y `Escape`.

## Fase 2 — Reutilización del estado actual de dispositivos
- hacer que el selector nuevo lea `availableInputDevices`, `selectedEntryDeviceId`, `entryPermissionStatus`;
- renderizar casos sin permiso / sin dispositivos / labels vacíos;
- abrir popover y lanzar refresh inmediato;
- activar polling solo mientras el popover está abierto.

## Fase 3 — Aplicación segura del cambio sin conversación en vuelo
- permitir que cambiar dispositivo solo actualice selección y persistencia si no hay captura activa;
- validar que el siguiente `startVoiceCapture()` usa ya el nuevo micro.

## Fase 4 — Cambio de dispositivo en caliente con reinicio controlado
- añadir rutina específica de reinicio de captura;
- cubrir reconfiguración de recorder + analyser + bola azul;
- bloquear o diferir cuando haya `voiceTurnInFlight`/`turnInFlight`.

## Fase 5 — Endurecimiento y UX de errores
- mensajes más precisos de fallback/reversión;
- estado visual de “aplicando cambio…”;
- pruebas manuales de desconexión, reconexión y errores de dispositivo ocupado.

# 14. Archivos concretos a tocar cuando se implemente

## Seguros / casi seguros
- `backend/interfaz_usuario_app/index.html`
  - añadir markup del selector y estilos asociados.

- `backend/interfaz_usuario_app/app.js`
  - ampliar estado UI;
  - render del selector;
  - polling del popover;
  - lógica de cambio de dispositivo;
  - reinicio controlado del pipeline de captura.

## Posibles, pero no necesariamente obligatorios en primera iteración
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`
  - solo si se detecta que alguna transición visual del avatar necesita una señal explícita adicional durante el reinicio del micrófono. A priori no debería ser necesario.

## No parece necesario tocar
- backend Python;
- endpoints API;
- TTS/STT del servidor;
- `backend/avatar_app/*` si el alcance se mantiene en `interfaz_usuario_app`.

# 15. Recomendación final

La implementación seria y segura no debe tratar este cambio como “añadir un dropdown”, sino como la incorporación de una **segunda superficie de control sobre un pipeline de audio ya sensible**.

Recomendación final concreta:

1. **Limitar el alcance inicial a micrófono (`audioinput`)**.
2. **Ubicar el selector en `.bar-top`, a la derecha, con popover ascendente**.
3. **Reutilizar el estado y heurísticas de dispositivos ya existentes** en el overlay de entrada.
4. **Separar selección visual de aplicación técnica del cambio**.
5. **Introducir una rutina explícita de reinicio controlado del pipeline de captura** para soportar cambio en caliente sin romper:
   - `MediaRecorder`
   - stream activo
   - analyser
   - bola azul
   - reanudación correcta al seguir en modo hablar
6. **Bloquear o diferir cambio durante `turnInFlight` / `voiceTurnInFlight`** para evitar condiciones de carrera.
7. **Mantener refresh activo solo mientras el popover está abierto**, con footer persistente `Buscando dispositivos…` y spinner.

La parte visual parece relativamente directa porque `.bar-top` ya tiene el hueco natural. La parte delicada es el cambio en caliente, porque hoy el flujo de audio está diseñado en torno a iniciar/parar captura por turnos, no por reconfiguración dinámica del dispositivo.
