# OpenAI Structured Outputs — reglas relevantes (captura 2026-04-09)

Fuente oficial principal:
- https://developers.openai.com/api/docs/guides/structured-outputs

Reglas relevantes usadas en la investigación:

1. El objeto root debe ser `object` y no `anyOf` en la raíz.
2. Todos los campos deben estar en `required` para Structured Outputs strict.
3. Para cada objeto, `additionalProperties` debe ser `false`.
4. `anyOf` es soportado con restricciones (subschemas válidos del subconjunto).
5. Hay keywords no soportadas en el subconjunto (`allOf`, `not`, `dependentRequired`, etc.; y restricciones extra para modelos fine-tuned).

Nota de investigación:
Nuestro validador local `validate_strict_json_schema(...)` no modela completamente estas restricciones del subconjunto OpenAI;
por diseño actual valida principalmente:
- correspondencia `properties` vs `required`
- `additionalProperties == false` en nodos objeto
