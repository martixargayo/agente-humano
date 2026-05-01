# Investigación E2E/diagnóstica del flujo de simulación (voz, STT, pipeline, keyboard_proxy)

## Alcance
Documento orientado a diagnóstico. No introduce fixes funcionales de producción.

## 1) Mapa integral de flujo

### Entrada texto (WRITE)
`handleSend` -> `runNegotiationTurnFromText(message)` -> `POST /negociacion/turn` -> pipeline conversacional -> `out.reply` -> render UI -> TTS/avatar opcional con `playTtsWithAvatar`. 

### Entrada voz (TALK)
`runEnterShortcutAction` o botón finalizar -> `handleFinishTurn` -> `stopVoiceCapture` -> Blob -> `transcribeAudio` -> `POST /stt_google` -> texto transcrito -> `runNegotiationTurnFromText(text)` -> pipeline -> respuesta -> TTS/avatar -> reapertura de micrófono (`startVoiceCapture`) si sigue en TALK.

### keyboard_proxy
`handleEmbeddedKeyboardProxy` valida origen/envelope/correlation -> `runEnterShortcutAction` -> en TALK termina en `handleFinishTurn`.

## 2) Hallazgos técnicos clave

1. `audioChunks` se limpia al iniciar captura y al cerrar en `onstop`; además hay limpieza en teardown.
2. `voiceTurnInFlight` se marca al principio de `handleFinishTurn` antes de await, reduciendo carreras de doble disparo.
3. Reapertura automática de micrófono tras turno exitoso en TALK.
4. El log `[embed] ACK final_result_saved recibido` se emite antes de validar tipo/ns/v; por eso puede aparecer para mensajes `keyboard_proxy` y confundir diagnóstico.
5. La frase genérica “No pude completar la generación...” sale de `_brain_fallback` en pipeline, no del frontend de voz.

## 3) Matriz de pruebas automatizadas (implementadas)

### A. API/backend
- `/stt_google` audio vacío -> 400.
- sin Google/OpenAI -> 503.
- Google runtime fail + OpenAI ausente -> 503.
- Google fail + OpenAI ok -> 200.
- OpenAI runtime fail -> 503.
- Se documenta ambigüedad de 503 (config ausente vs runtime fail).

### B. Frontend runtime/harness (Node via pytest)
- `transcribeAudio`: 503, 400, network error, JSON malformado, 200 con texto vacío, 200 válido.
- `handleFinishTurn`: blob vacío no llama STT, errores liberan `voiceTurnInFlight`, reintento posible.
- doble invocación casi simultánea de `handleFinishTurn` -> una sola llamada STT.
- verificación origen frase fallback (pipeline sí / frontend no).

### C. keyboard_proxy/regresión existente
- contrato de seguridad y dedupe por correlation_id.
- bloqueo por busy/turnInFlight/voiceTurnInFlight.

## 4) Pruebas manuales de 20 minutos (pendientes)

### Escenario A: Altavoces + TTS
- 3 turnos cortos, 3 largos, 1 sin hablar.
- objetivo: detectar transcripción del agente (posible eco).

### Escenario B: Auriculares + TTS
- repetir A.
- si desaparece anomalía -> indicio fuerte de autocaptura TTS.

### Escenario C: TTS/avatar muteado
- repetir A.
- si desaparece anomalía -> indicio fuerte de autocaptura TTS.

### Escenario D: finalizar inmediato
- validar blob.size, duration_ms y resultado STT.

### Escenario E: mic abierto 30–60s
- medir crecimiento blob.size y transcript_len (captura larga).

### Escenario F: botón vs Enter local vs keyboard_proxy
- comparar número de llamadas STT por acción.

## 5) Taxonomía/patrones a detectar
- AUDIO_EMPTY_REAL
- AUDIO_SILENCE_WITH_BYTES
- STT_PROVIDER_FAIL
- STT_OK_PIPELINE_FALLBACK
- CAPTURE_TOO_LONG
- POSSIBLE_TTS_ECHO
- DOUBLE_TRIGGER
- STATE_STUCK

## 6) Observabilidad mínima recomendada (debug)
Frontend por turno:
- `voice_turn_id`, source, correlation_id
- capture_start/stop/duration
- chunks_count, blob.size, blob.type
- tts_playing_at_mic_open/close
- stt_status, transcript_len
- pipeline_called, pipeline_result, error_phase

Backend:
- audio_bytes, content_type
- provider_attempted, provider_result
- transcript_len
- pipeline fallback reason
- status final

## 7) Estado de hipótesis con evidencia actual
- Confirmada: STT puede devolver 200 con texto y aun así existir fallback en pipeline en otros turnos.
- Confirmada: 503 de STT es ambiguo (no-config vs runtime fail).
- Poco probable como causa principal global: audio vacío en todos los casos.
- Probable y abierta: captura no intencional/larga y posible eco TTS.
- Riesgo bajo-medio: doble disparo; guardas existen, pero se recomienda observabilidad por turno.

## 8) Recomendación del primer fix (aún no implementado)
1. Primero, añadir observabilidad por turno (sin cambiar UX ni negocio).
2. Segundo, aplicar reglas de ciclo de captura (por ejemplo, no reabrir mic hasta estado TTS inactivo verificado) si los datos confirman eco/autocaptura.
3. Tercero, desambiguar errores STT 503 (config vs runtime) para diagnóstico operativo.

## 9) Activación de observabilidad mínima por turno (voz)

Frontend (apagado por defecto):
- Activar por localStorage: `localStorage.setItem('gce_voice_debug', '1')`
- O activar por query param: `?voice_debug=1`
- Desactivar: `localStorage.removeItem('gce_voice_debug')`

Backend STT (apagado por defecto):
- Activar con env: `GCE_VOICE_DEBUG=1`

### Ejemplos de eventos esperados
- `voice_turn_start` (source, correlation_id, flags de in-flight)
- `voice_capture_stop_result` (duration_ms, blob_size, blob_type)
- `voice_blob_empty`
- `stt_request` / `stt_response`
- `pipeline_call` / `pipeline_result`
- `voice_turn_error` / `voice_turn_end`

### Garantías de privacidad de esta instrumentación
- No se loguea audio.
- No se loguea texto completo transcrito.
- No se loguean mensajes completos de usuario/agente.
- Se registran únicamente metadatos (sizes, status, longitudes y estados).
