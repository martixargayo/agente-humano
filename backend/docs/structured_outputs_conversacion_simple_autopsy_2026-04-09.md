# Autopsia técnica profunda: Structured Outputs en `conversacion_simple` (2026-04-09)

## Alcance y método

Objetivo: reconstruir el schema exacto enviado al provider y explicar por qué el error real (`Extra required key 'memory_episodic_append' supplied`) persiste aunque localmente no se reproduzca.

### Comandos ejecutados

1. Búsqueda de rutas de ejecución y puntos `responses.create`.
2. Revisión de helper compartido y pipeline `conversacion_simple`.
3. Reconstrucción/instrumentación local con cliente fake para capturar **exactamente** `text.format.schema`, `name`, `strict` justo antes de `responses.create`.
4. Comparación nodo a nodo de:
   - base (`model_json_schema()`),
   - normalizado,
   - efectivamente enviado.
5. Repetición del proceso para summarizer.
6. Verificación de metadata de runtime (`get_runtime_version_info`) y revisión de historia de commits sobre la normalización.

## Contrato oficial de OpenAI (fuente externa de verdad)

Fuente principal: https://platform.openai.com/docs/guides/structured-outputs (redirige a developers).

Reglas confirmadas:

1. **Root schema**: debe ser objeto, no `anyOf` en raíz.
2. **Strict + required**: todos los campos del objeto deben estar en `required`.
3. **Opcionales**: modelar como unión con `null`, no quitando claves de `required`.
4. **`additionalProperties: false`**: requerido para objetos en este modo.
5. **Subset JSON Schema**: en strict se soporta un subconjunto; usar keywords no soportadas produce error.

Estas reglas aparecen explícitas en la guía (secciones “Root objects…”, “All fields must be required”, “union type with null”, “subset”).

## Flujo real (optimizador → provider)

1. `run_sandbox_turn()` en optimizador delega al adapter de flujo `conversacion_simple` cuando `flow_id == "conversacion_simple"`.
2. El adapter llama `run_conversacion_simple_turn()`.
3. `run_conversacion_simple_turn()` llama `_call_brain_structured()`.
4. `_call_brain_structured()` construye schema con:
   - `BrainOutput.model_json_schema()`
   - `normalize_schema_for_strict_json_schema(...)`
   - validación `validate_strict_json_schema(...)`
5. Justo antes de `client.responses.create(...)`, se envía:
   - `text.format.type = "json_schema"`
   - `text.format.name = "BrainOutput"`
   - `text.format.schema = normalized_schema`
   - `text.format.strict = true`

Misma mecánica para summarizer con `SummarizerOutput`.

## Reconstrucción REAL del schema enviado (captura efectiva)

Artefacto generado por instrumentación: `backend/docs/artifact_structured_outputs_conversacion_simple_forensics_2026-04-09.json`.

### BrainOutput

- `name`: `BrainOutput`
- `strict`: `true`
- Hashes:
  - base: `e02e315035b6e263`
  - normalizado: `a9c3c1309609005f`
  - enviado: `a9c3c1309609005f`
- Resultado clave: **normalizado == enviado** (mismo hash).
- `first_mismatch`:
  - base: missing en raíz (`observability`) y en `$defs.BrainStatePatch` (`memory_episodic_append`)
  - normalizado: `null`
  - enviado: `null`

### SummarizerOutput

- `name`: `SummarizerOutput`
- `strict`: `true`
- Hashes:
  - base: `49cfdc476ba05132`
  - normalizado: `894a4a59c377b566`
  - enviado: `894a4a59c377b566`
- Resultado clave: **normalizado == enviado**.
- `first_mismatch`:
  - base: faltantes en root
  - normalizado: `null`
  - enviado: `null`

## Comparativa exhaustiva por etapas

### A) Brain base vs normalizado

- Root:
  - base `properties`: `schema_version,status,assistant_response,state_patch,observability`
  - base `required`: `schema_version,status,assistant_response,state_patch`
  - normalizado `required`: incluye también `observability`.
- `$defs.BrainStatePatch`:
  - base `properties`: `conversation_state,memory_working,memory_episodic_append`
  - base `required`: `conversation_state,memory_working`
  - normalizado `required`: incluye `memory_episodic_append`.

### B) Brain normalizado vs enviado

- Igualdad estructural efectiva (mismo hash).
- No aparece `memory_episodic_append` en root `required`.
- `memory_episodic_append` queda confinado a `$defs.BrainStatePatch.required`.

### C) Summarizer base vs normalizado vs enviado

- Normalización corrige faltantes en root.
- No hay mismatch adicional ni extra keys.
- Envío coincide exactamente con normalizado.

## Nodo exacto del error reportado y por qué apunta a raíz

Error real observado:

> Invalid schema for response_format 'BrainOutput': ... Extra required key 'memory_episodic_append' supplied.

En la sintaxis del provider, `In context=()` significa **raíz**.

Por tanto, el nodo exacto implicado es:

- **Ruta JSON**: `$`
- **`required` contiene**: `memory_episodic_append`
- **`properties` de ese mismo nodo no contiene**: `memory_episodic_append`

Para validar que ese patrón produce exactamente ese tipo de mismatch, en la autopsia se construyó un schema sintético “contaminado” añadiendo `memory_episodic_append` al `required` raíz. Resultado del validador interno:

- `first_mismatch.kind = extra_required`
- `first_mismatch.path = "$"`
- `extra_keys = ["memory_episodic_append"]`

Esto alinea exactamente con el error del provider.

## Hipótesis pedidas (1–9): veredicto con evidencia

1. **Runtime desplegado no coincide con repo local** → **ALTAMENTE PROBABLE**.
   - Local actual no reproduce contaminación raíz.
   - El schema enviado local coincide con normalizado válido.

2. **Ruta efectiva distinta en optimizador altera schema** → **NO SOPORTADO en código actual de conversacion_simple**.
   - El adapter de `conversacion_simple` va directo a `run_conversacion_simple_turn`.

3. **Helper compartido no es el último transformador** → **NO en esta ruta**.
   - En `_call_brain_structured` el schema que se pasa a `responses.create` es el normalizado recién calculado.

4. **Mutación posterior tras normalizar** → **NO EVIDENCIA en ruta local actual**.
   - Hash normalizado == hash enviado.

5. **Aliasing/referencias compartidas contaminan required** → **NO EVIDENCIA en helper actual**.
   - El helper reconstruye dict/list recursivamente; no muta in-place el input.

6. **Mezcla de required entre root y `$defs`** → **NO EVIDENCIA en build actual**.
   - Captura real muestra separación correcta.

7. **Serialización/reconstrucción cambia árbol final** → **NO EVIDENCIA local**.
   - El objeto capturado justo antes de `responses.create` es válido.

8. **Divergencia brain vs summarizer** → **NO en runtime local actual**.
   - Ambos normalizan y envían schemas válidos.

9. **Tests no detectan desalineación estructural** → **PARCIALMENTE RESUELTO, aún insuficiente en cobertura E2E desplegada**.
   - Sí hay tests unitarios de `extra_required` en helper.
   - Pero no hay garantía desde evidencia de producción de que el deploy que falla esté ejecutando este código/hash.

## Runtime vs repo (metadata de versión)

`get_runtime_version_info()` devuelve:

- `service_version/build_id/deploy_env`: `null` si no se inyectan envs.
- fallback a git local para `git_commit` y `git_branch`.

En este entorno local:

- `git_commit = b662b5ad2cb8457712727e639426a668688261be`
- `git_branch = work`
- envs de build/deploy vacíos.

Conclusión: si en producción esos campos están vacíos o no se persisten en trazas, se pierde capacidad de probar paridad runtime↔repo. Ese gap explica por qué “local limpio” puede coexistir con “runtime fallando”.

## Causa raíz más defendible

Con evidencia disponible en este repo y reconstrucción exacta local:

1. **No existe en el código actual una transformación que mueva `memory_episodic_append` desde `$defs.BrainStatePatch` hacia root `required`.**
2. El error real solo es posible si el schema enviado por ese runtime específico ya llega contaminado en raíz.
3. Eso apunta a **desfase runtime/repo o ruta de ejecución distinta en el entorno que falla** (build viejo, servicio paralelo, o binario/proceso no actualizado), más que a un bug vigente del helper actual.

## Qué tocar después (sin aplicar fix ahora)

1. Añadir logging estructurado en producción del bloque exacto `text.format` (name, strict, hash, first_mismatch, root_required, root_properties).
2. Registrar explícitamente `runtime_version.git_commit` y `build_id` en cada traza de fallo provider.
3. Añadir comparación automática `schema_hash` esperado por commit vs hash real enviado.
4. Cortar ejecución antes de provider si `validate_strict_json_schema(...).valid == false` con detalle de ruta mismatch.
5. Extender pruebas de integración para forzar aserción de igualdad hash entre schema normalizado y schema enviado en brain + summarizer.

---

## Anexo: evidencia de historia de cambios relevante

La historia de commits muestra cambios recientes en normalización estricta (`ba5c73f`, `c21107d`, `7f6bff6`, `ab638f8`), lo que refuerza la hipótesis de paridad de despliegue: un entorno no actualizado puede emitir un árbol distinto al reconstruido hoy.
