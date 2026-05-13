# Diagnóstico del fallback “No pude completar la generación del turno” en Railway

## Qué significa el mensaje

El texto:

> No pude completar la generación del turno en este intento. ¿Puedes repetir tu último mensaje?

no lo genera el modelo como respuesta conversacional normal. Es el fallback determinista de `conversacion_simple` cuando el pipeline no consigue convertir la llamada del nodo `brain` en un `BrainOutput` válido.

## Dónde queda registrado

Buscar en los logs de Railway por estos eventos:

- `conversacion_simple_brain_fallback_activated`: confirma que se entregó el fallback al usuario e incluye `fallback_reason_code`, `retry_attempted`, `retry_succeeded`, `retry_reason` y metadatos de parseo.
- `conversacion_simple_structured_call_failed stage=brain`: indica excepción del proveedor/OpenAI, con tipo, status code y code sanitizados.
- `conversacion_simple_brain_json_parse_error`: la respuesta tuvo texto, pero no era JSON parseable.
- `conversacion_simple_brain_retry_succeeded`: el retry posterior corrigió una salida no JSON.
- `conversacion_simple_brain_retry_failed`: el retry posterior también falló.
- `conversacion_simple_brain_empty_output_text`: la llamada volvió sin `output_text`; desde este parche incluye metadata segura como `response_status`, `response_incomplete_reason`, `response_output_count`, tipos de output y código de error del response, sin volcar contenido del usuario ni salida completa del modelo.

Además, el último trace de sesión guarda:

- `brain_fallback_reason_code`
- `memory_observability.brain_provider_exception` si hubo excepción del proveedor.
- `memory_observability.brain_provider_response_diagnostics` si hubo respuesta del proveedor sin texto utilizable o metadata estructural disponible.
- `memory_observability.brain_schema_observability` para descartar problemas de schema strict.
- `stage_timings_ms` / `stage_timings_precise_ms` para ver si el fallo coincide con latencias o timeouts.

## Interpretación rápida de `fallback_reason_code`

- `provider_exception`: fallo en la llamada al proveedor. Revisar status code, rate limits, timeouts, errores 5xx o configuración de modelo.
- `empty_output_text`: el proveedor devolvió una respuesta sin texto extraíble. Revisar `brain_provider_response_diagnostics`, especialmente `response_status` e `response_incomplete_reason`.
- `json_parse_error`: hubo texto, pero no era JSON válido. El pipeline intenta un retry automático; si `retry_succeeded=false`, el usuario ve el fallback.
- `validation_error_after_parse`: hubo JSON parseable, pero no cumplía el schema `BrainOutput`.
- `schema_preflight_invalid`: el schema local no pasó la validación antes de llamar al proveedor.
- `client_unavailable`: no se creó cliente OpenAI, normalmente por falta de `OPENAI_API_KEY` o error inicializando el cliente.

## Prompt para la IA de Railway

Pega este prompt en la IA de Railway y adjunta/selecciona logs del periodo afectado:

```text
Analiza estos logs de Railway para encontrar la causa de respuestas intermitentes con el texto exacto:
“No pude completar la generación del turno en este intento. ¿Puedes repetir tu último mensaje?”

Contexto técnico:
- Ese texto es un fallback determinista de la app, no una respuesta normal del modelo.
- El flujo afectado es conversacion_simple, especialmente contextos como negociacion_sala_reuniones / sala reuniones.
- La app debería registrar eventos con estos nombres:
  - conversacion_simple_brain_fallback_activated
  - conversacion_simple_structured_call_failed stage=brain
  - conversacion_simple_brain_empty_output_text
  - conversacion_simple_brain_json_parse_error
  - conversacion_simple_brain_retry_succeeded
  - conversacion_simple_brain_retry_failed
  - conversacion_simple_schema_preflight_failed stage=brain

Tareas:
1. Agrupa los fallos por fallback_reason_code.
2. Para cada fallo, extrae session, turn_id, timestamp aproximado, model_attempted, model_succeeded, retry_attempted, retry_succeeded, retry_reason y user_message_len.
3. Si hay provider_exception, extrae provider_exception_type, provider_exception_status_code, provider_exception_code, provider_model_target y provider_exception_message sanitizado.
4. Si hay empty_output_text, extrae response_status, response_incomplete_reason, response_output_count, response_output_item_types, response_first_output_status y response_error_code.
5. Si hay json_parse_error, indica si el retry funcionó; si no funcionó, resume parse_meta sin incluir texto del usuario ni contenido raw del modelo.
6. Busca correlaciones temporales: picos, cold starts, deploys, timeouts, memoria, CPU, rate limits o errores 429/5xx.
7. Dime cuál es la causa más probable y qué evidencia la soporta.
8. Propón acciones concretas para mitigarlo, separando: configuración Railway, OpenAI/provider, prompt/schema, max_output_tokens, retry/fallback y observabilidad.

Importante:
- No pegues ni resumas contenido privado de conversaciones.
- Prioriza logs con los eventos anteriores y las líneas inmediatamente anteriores/posteriores.
- Si falta información, enumera exactamente qué campos/logs faltan.
```

## Recomendación de búsqueda manual en Railway

Empieza con estos filtros:

```text
conversacion_simple_brain_fallback_activated OR conversacion_simple_structured_call_failed OR conversacion_simple_brain_empty_output_text OR conversacion_simple_brain_json_parse_error
```

Luego acota por la frase del fallback o por una sesión afectada si el frontend/backend expone `session_id`.
