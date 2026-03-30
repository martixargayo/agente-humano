# Diagnóstico técnico: evolución de `prompt_io_mapping` hacia transformación profunda

Este documento resume el estado real del sistema actual y propone un diseño incremental para soportar transformación profunda (nested/arrays/value aliases) manteniendo contratos canónicos internos.

## Hallazgos clave

- `prompt_io_mapping.v1` está modelado para reglas por **campo top-level** (`inputs`/`outputs` como `dict[str, FieldMappingRule]`).
- La validación de reglas contra nodos usa `model_fields.keys()` del modelo pydantic de entrada/salida de cada nodo; por tanto, solo admite claves top-level canónicas.
- La adaptación de input y normalización de output operan sobre `dict` de primer nivel (sin traversal recursivo).
- La adaptación de schema de salida modifica solo `properties` top-level del `model_json_schema`.
- El runtime ya tiene puntos de inserción correctos para una futura v2 (adapt input, output schema, normalize output), pero la implementación actual de esas piezas es superficial.

## Recomendación

Mantener `v1` estable e introducir `prompt_io_mapping.v2` con:

1. compilación de reglas path-based;
2. transformación recursiva para input/output;
3. adaptación recursiva del schema visible de salida;
4. normalización visible->canónico también recursiva;
5. validación fail-fast con diagnóstico por nodo/path/regla.
