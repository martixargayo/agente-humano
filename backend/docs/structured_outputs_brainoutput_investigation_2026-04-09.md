# Investigación técnica: error Structured Outputs en `BrainOutput` (2026-04-09)

## Ruta real de ejecución (optimizador -> conversacion_simple)

1. `run_sandbox_turn()` del optimizador fija `failing_stage = "execute_turn_with_contract"` antes de delegar al adapter.
2. Si `flow_id == "conversacion_simple"`, el adapter llama `run_conversacion_simple_turn()`.
3. En `_call_brain_structured()`, la llamada a `client.responses.create()` envía `text.format.schema` con:
   - `name = "BrainOutput"`
   - `schema = normalize_schema_for_strict_json_schema(BrainOutput.model_json_schema())`
   - `strict = true`

## Reconstrucción del schema en 3 etapas

Se ejecutó instrumentación local con el mismo código de runtime (mismo wiring de `_call_brain_structured`) para capturar el `schema` final que va a `responses.create`.

### 1) `BrainOutput.model_json_schema()` (base, sin normalizar)

- Primer mismatch encontrado: en raíz (`$`), falta `observability` en `required`.
- Segundo mismatch: en `$defs.BrainStatePatch`, falta `memory_episodic_append` en `required`.

Valores observados:

- `BASE_ROOT_REQUIRED = ["schema_version", "status", "assistant_response", "state_patch"]`
- `BASE_ROOT_PROPERTIES = ["schema_version", "status", "assistant_response", "state_patch", "observability"]`
- `BASE_BRAINSTATEPATCH_REQUIRED = ["conversation_state", "memory_working"]`
- `BASE_BRAINSTATEPATCH_PROPERTIES = ["conversation_state", "memory_working", "memory_episodic_append"]`

### 2) Schema tras `normalize_schema_for_strict_json_schema(...)`

- `NORMALIZED_FIRST_MISMATCH = None`.
- En raíz:
  - `required = ["schema_version", "status", "assistant_response", "state_patch", "observability"]`
  - `properties = ["schema_version", "status", "assistant_response", "state_patch", "observability"]`
- En `$defs.BrainStatePatch`:
  - `required = ["conversation_state", "memory_working", "memory_episodic_append"]`
  - `properties = ["conversation_state", "memory_working", "memory_episodic_append"]`

### 3) Schema final enviado por `_call_brain_structured()`

Se capturó el `kwargs["text"]["format"]["schema"]` real de la llamada:

- `FINAL_FIRST_MISMATCH = None`
- `FINAL_ROOT_REQUIRED` coincide exactamente con `FINAL_ROOT_PROPERTIES`
- `FINAL_BRAINSTATEPATCH_REQUIRED` coincide exactamente con `FINAL_BRAINSTATEPATCH_PROPERTIES`
- `FINAL_ROOT_ADDITIONALPROPERTIES = False`
- `FINAL_BRAINSTATEPATCH_ADDITIONALPROPERTIES = False`

## Hallazgo clave

Con el código actual del repositorio, **no se reproduce** un estado donde:

- `required` raíz incluya `memory_episodic_append`, y
- `properties` raíz no lo incluya.

En el árbol válido actual, `memory_episodic_append` aparece únicamente dentro de `$defs.BrainStatePatch` (que es exactamente donde debe estar).

## Inspección del helper compartido

`normalize_schema_for_strict_json_schema`:

- no muta in-place el objeto de entrada (crea dict/list nuevos por recursión),
- recorre recursivamente dicts/listas completos,
- toca `$defs` porque recorre todo el árbol,
- asigna `required = list(properties.keys())` **por nodo** (no usa estado global),
- no presenta aliasing interno por diseño (salida reconstruida nodo por nodo).

Conclusión técnica: en este commit, el helper **no muestra un bug estructural** de “arrastre” de `required` entre niveles.

## Revisión del summarizer

Mismo patrón:

- `SummarizerOutput.model_json_schema()` base llega con faltantes en `required` para campos default.
- Tras normalizar: `SUM_NORM_FIRST_MISMATCH = None` y conteos raíz iguales (`14 == 14`).

No se observó la anomalía de “extra required key” en summarizer bajo esta ruta.

## Gap de tests que sí existe

Los tests actuales de normalización en runtime usan `_collect_required_mismatches()`, pero esa utilidad **solo detecta faltantes** (`properties - required`) y **no detecta sobrantes** (`required - properties`).

Por eso este tipo de regresión (“Extra required key ... supplied”) puede pasar inadvertida incluso si hubiera aparecido en otra ruta.
