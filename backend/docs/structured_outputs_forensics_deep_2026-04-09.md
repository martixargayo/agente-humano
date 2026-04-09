# Investigación forense profunda — Structured Outputs en `conversacion_simple` (2026-04-09)

## Resumen corto
Esta investigación confirma, con captura del body HTTP serializado vía SDK (`httpx.MockTransport`), que en el entorno local el schema de `BrainOutput` **no se muta** entre:
1) schema normalizado/validado localmente,
2) `provider_request` trazado,
3) body HTTP final enviado por el SDK.

Por tanto, en local **no se reproduce** una discrepancia de tipo “el SDK alteró `required` en root”.

## Qué se instrumentó
- Script forense nuevo: `backend/scripts/forensics_structured_outputs_wire_capture.py`.
- Reporte JSON reproducible: `docs/forensics_structured_outputs_wire_capture_report.json`.
- Tests forenses nuevos: `backend/tests/test_forensics_structured_outputs_wire_capture.py`.

## Pregunta central
¿Existe diferencia entre `brain_provider_request` y el body HTTP real serializado por el SDK?

## Resultado
No, en este entorno:
- `brain.provider_request_equals_http_body = true`
- `brain.schema_equals_normalized = true`
- `raw_http_equivalence.equal = true`

Además:
- root `required` **no** contiene `memory_episodic_append`.
- `BrainStatePatch.required` sí contiene `memory_episodic_append` (como corresponde).

## Contraste con hipótesis H1/H2/H3
- H1 (snapshot ≠ body final): **no soportada** en local.
- H2 (transform posterior al snapshot): **no soportada** en local.
- H3 (SDK muta schema): **no soportada** en local con OpenAI SDK `2.31.0`.

## Hallazgo adicional importante (validador local)
`validate_strict_json_schema(...)` cubre invariantes de strict-mode internos (required/properties/additionalProperties),
pero **no cubre todo el subconjunto OpenAI**. Ejemplo: un schema con root `anyOf` queda `valid=true` localmente,
aunque la documentación de OpenAI lo restringe.

## Implicación
La discrepancia runtime (“OpenAI rechaza schema que localmente luce correcto”) queda más consistente con:
1) drift de entorno/runtime (código o versión distinta en despliegue), o
2) restricción de subconjunto OpenAI no modelada por nuestro validador local.

## Limitación explícita
No fue posible ejecutar una llamada real a OpenAI desde este entorno porque no hay `OPENAI_API_KEY` en la sesión actual.
La captura de body se hizo de forma forense con transporte mockeado en el borde real del SDK.

