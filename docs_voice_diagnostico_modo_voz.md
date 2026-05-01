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

## 10) Cómo validar que la observabilidad funciona

### Frontend
1. Abrir consola del iframe.
2. Ejecutar: `localStorage.setItem('gce_voice_debug', '1')`.
3. Recargar iframe.
4. Realizar un turno de voz.
5. Verificar secuencia mínima:
   - `voice_turn_start`
   - `voice_capture_stop_result`
   - `stt_request`
   - `stt_response`
   - `pipeline_call`
   - `pipeline_result`
   - `voice_turn_end`

### Backend (Railway)
1. Definir variable: `GCE_VOICE_DEBUG=1`.
2. Reiniciar/redeploy.
3. Realizar un turno de voz.
4. Verificar eventos:
   - `google_client_init`
   - `stt_backend_request`
   - `provider_attempt`
   - `provider_result`
   - `stt_backend_response`

### Ejemplos interpretables
- Turno normal: `stt_response ok=true` + `pipeline_result ok=true`.
- STT 503: `stt_backend_response status=503` y `provider_result ... ok=false` para ambos.
- Pipeline fallback: STT 200 + log `conversacion_simple_brain_fallback_emitted`.
- Posible TTS echo: transcript_len alto/inesperado en turnos sin habla real y patrón dependiente de altavoz.
- Doble envío: más de un `stt_request` para mismo `voice_turn_id` (o dos `voice_turn_start` casi simultáneos por una única interacción).

## 11) Configuración STT recomendada (Railway/local)

- Variable recomendada explícita: `GOOGLE_STT_SAMPLE_RATE_HERTZ=48000`.
- Para audio de navegador `audio/webm;codecs=opus` (WEBM_OPUS), el backend debe resolver sample rate válido y **nunca** enviar `sample_rate_hertz=0`.
- Compatibilidad mantenida para nombres heredados:
  - `GOOGLE_STT_SAMPLE_RATE_HERTZ`
  - `GOOGLE_STT_SAMPLE_RATE`
  - `SAMPLE_RATE`
- Si no hay sample rate válido y encoding es Opus (`WEBM_OPUS` / `OGG_OPUS`), se usa fallback seguro `48000`.
- Si el encoding no es Opus y no hay sample rate válido, el campo se omite.

### Bug histórico resuelto
- Causa raíz observada: Google STT runtime error por `sample_rate_hertz=0` con Opus.
- Mitigación: parseo seguro + fallback Opus 48000 + omisión en no-Opus cuando aplica.

## 12) Mitigación inicial de json_parse_error (brain)

- Se plantea (y valida por tests) un retry único cuando el primer intento de brain falla en `json_parse_error`.
- El retry mantiene `text.format=json_schema` `strict=true` y añade instrucción de reparación: devolver solo objeto JSON sin markdown/fences/texto extra.
- Si el retry funciona: no hay fallback.
- Si el retry falla: se mantiene fallback actual (`_brain_fallback`) con `fallback_reason_code=json_parse_error`.
- Observabilidad segura: se registran solo metadatos (`output_len`, `first_non_ws_char`, `starts_with_code_fence`, `looks_like_json_object`, `parse_error_pos`, `retry_attempted`, `retry_succeeded`) sin contenido completo.

## 13) Primer PR para audio largo (sin split)

Routing por duración (`recording_duration_ms`):
- `recording_duration_ms` ausente o <= `GOOGLE_STT_SYNC_MAX_DURATION_MS`: Google sync primero, fallback OpenAI.
- `GOOGLE_STT_SYNC_MAX_DURATION_MS < recording_duration_ms <= VOICE_MAX_DURATION_MS`: OpenAI STT directo (se salta Google sync).
- `recording_duration_ms > VOICE_MAX_DURATION_MS`: rechazo controlado (`Audio demasiado largo...`).

Variables recomendadas en Railway:
- `GOOGLE_STT_SYNC_MAX_DURATION_MS=55000`
- `VOICE_MAX_DURATION_MS=120000`

`stt_mode` esperado en logs debug:
- `google_sync`
- `google_sync_then_openai_fallback`
- `openai_direct_long_audio`
- `rejected_too_long`

Nota: split 60+60 queda como hardening posterior.
