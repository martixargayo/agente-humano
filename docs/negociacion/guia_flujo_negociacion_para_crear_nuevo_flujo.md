# Guía súper detallada del flujo de negociación (y cómo crear un flujo/contexto nuevo)

> Objetivo: explicar **de punta a punta** cómo funciona el runtime de negociación y qué piezas debes tocar para crear un nuevo flujo/contexto sin romper contratos.

---

## 1) Mapa mental rápido

El backend separa claramente:

1. **Superficies de entrada** (interfaces):
   - `interfaz_usuario` (producto público principal).
   - `optimizador` (sandbox para experimentación y overrides).
   - `/negociar` legacy (compatibilidad antigua).
2. **Contrato de contexto**: toda ejecución stateful exige que coincidan:
   - contexto ligado a sesión,
   - contexto efectivo del turno,
   - contexto de la config/prompt dir.
3. **Pipeline cognitivo** (nodos):
   - `memory` + `phase_classifier` en paralelo/stateless.
   - `planner` y `executor` en secuencia/stateless.
4. **Assets por contexto**:
   - prompts, persona, brief, phase cards, mapping de IO y presentación.
5. **Trazas y observabilidad**:
   - cada turno guarda trace con `context_meta` + `entry_contract`.

---

## 2) Punto de entrada y superficies (interfaces)

### 2.1 `interfaz_usuario` (ruta estable de producción)

- Router: `backend/interfaz_usuario/__init__.py`.
- Endpoints relevantes:
  - `POST /api/interfaz_usuario/sessions/bootstrap`
  - `POST /api/interfaz_usuario/negociacion/turn`
  - `POST /api/interfaz_usuario/sessions/finalize`
- Servicio principal: `backend/interfaz_usuario/services.py`.

Flujo resumido:

1. Bootstrap crea/rehidrata sesión, valida superficie y liga contexto (`ensure_session_context`).
2. Turno adquiere lock, toca TTL, resuelve contexto, arma config stateful, construye `TurnExecutionContext` y ejecuta `execute_turn_with_contract`.
3. Devuelve reply + metadatos (trace ids, contract, estado del botón de finalizar, etc.).

### 2.2 `optimizador` (sandbox de experimentación)

- Router: `backend/negociacion/optimizador/__init__.py`.
- Servicio: `backend/negociacion/optimizador/services.py`.

Particularidades:

- Soporta **overrides** (prompts/config/contextual), clonación de sesión, versionado de intentos y comparativas entre turnos.
- Usa exactamente el mismo contrato de ejecución (`execute_turn_with_contract`) para no desalinearse de producción.
- Agrega telemetría de intentos (`optimizador_attempt_traces`) con categorías de error y reintentos.

### 2.3 `/negociar` legacy

- Endpoint deprecated en `backend/api/app.py`.
- Servicio `backend/negociacion/services/legacy_negociar_service.py`.

Sigue siendo stateful y exige `context_id` explícito; devuelve header de deprecación.

---

## 3) Contrato de contexto: la parte más importante

La robustez del sistema viene de aquí.

### 3.1 Resolver de contextos oficiales

Archivo: `backend/negociacion/contexts/resolver.py`.

- Contextos oficiales viven en `backend/negociacion/contexts/<context_id>/`.
- Cada contexto debe tener `manifest.json` y archivos requeridos:
  - prompts dir,
  - `assets/persona.json`,
  - `assets/negotiation_brief.json`,
  - `assets/phase_cards.json`,
  - `assets/phase_classifier_card.json`.
- Si falta algo, el contexto no se considera oficial.

### 3.2 Binding de sesión

Archivo: `backend/negociacion/contexts/session_binding.py`.

- La sesión guarda el contexto en `world_state["negotiation_context"]`.
- `ensure_session_context`:
  - reutiliza contexto ya ligado,
  - bloquea cambios conflictivos (`SessionContextConflictError`),
  - o liga un contexto nuevo si la sesión aún no tenía uno.

### 3.3 Selección pública `context_id` vs `public_slug`

Archivo: `backend/negociacion/contexts/public_mapping.py`.

- Permite bootstrap con `context_id`, `public_slug`, o ninguno (default).
- Si llegan ambos y no coinciden, falla por conflicto.

### 3.4 Validación pre-ejecución del turno

Archivo: `backend/negociacion/orchestration/turn_context_validator.py`.

Antes de ejecutar el pipeline, se valida que:

1. exista `turn_context` en stateful;
2. `effective_context_id` exista y no esté vacío;
3. sesión ligada == contexto efectivo;
4. config derive al mismo contexto;
5. `prompts_dir` pertenezca al mismo contexto.

Si algo no cuadra: error explícito (`ContextMismatchError`, `InvalidConfigContextError`, etc.).

---

## 4) Ejecución de turno: contrato y pipeline

### 4.1 Envoltura contractual

Archivo: `backend/negociacion/orchestration/turn_contract.py`.

`execute_turn_with_contract` hace:

1. infiere stateful si hay sesión ligada/contexto;
2. obliga `turn_context` cuando aplica;
3. valida contexto (`validate_turn_context_pre_execution`);
4. ejecuta `run_negotiation_cognitive_turn`;
5. inyecta `context_meta` + `_entry_contract` en la última traza.

### 4.2 Config de pipeline

Archivo: `backend/negociacion/orchestration/flow_config.py`.

- `build_negotiation_pipeline_config` resuelve contexto y establece:
  - `prompts_dir` contextual,
  - modelos por nodo,
  - flags de guardrails/traces,
  - límites de mensajes.
- `run_negotiation_cognitive_turn` vuelve a validar coherencia context/config y luego corre el turno.

### 4.3 Nodos y contratos de datos

Archivos:
- `backend/negociacion/nodes/memory_node.py`
- `backend/negociacion/nodes/phase_classifier_node.py`
- `backend/negociacion/nodes/planner_node.py`
- `backend/negociacion/nodes/executor_node.py`

Cada nodo tiene `Input`/`Output` pydantic con `extra="forbid"` para contratos estrictos.

Orden real de ejecución:

1. `memory` y `phase_classifier` en paralelo (stateless).
2. actualización de estado canónico intermedio.
3. `planner` en secuencia.
4. `executor` en secuencia.
5. guardrail de salida + persistencia de estado + trace.

---

## 5) Estado canónico y persistencia

Archivo: `backend/negociacion/state/canonical_state.py` + `sessions/state.py`.

- El estado de negociación vive en `world_state["negotiation_canonical"]`.
- Además se persisten:
  - diálogo reciente compacto,
  - trazas por turno,
  - ids de threading OpenAI (`conversation_id`, `previous_response_id`).
- Defaults de persona/brief pueden cargarse desde contexto o fallback de emergencia.

---

## 6) Prompt IO mapping (capa avanzada)

Archivo: `backend/negociacion/contexts/prompt_io_mapping.py`.

Esta capa permite adaptar los payloads sin cambiar los modelos internos:

- renombrar/ocultar campos en input/output,
- transformar esquema visible,
- versión v2 con paths anidados y alias de valores.

Uso práctico: mantener el contrato interno estable mientras experimentas formato externo de prompts/salidas por contexto.

---

## 7) Presentación/UI contextual

Archivos:
- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/interfaz_usuario/presentation_models.py`

- Carga defaults globales + overrides por contexto (`presentation/presentation_config.json`).
- Normaliza assets relativos a rutas públicas `/interfaz_usuario/context-assets/{context_id}/...`.
- Esto desacopla “cómo piensa el agente” de “cómo se ve en la UI”, pero ambos cuelgan del mismo contexto.

---

## 8) Cómo crear un nuevo flujo/contexto (checklist operativo)

> Nota: en esta arquitectura actual, la forma segura de “nuevo flujo” es **nuevo contexto oficial dentro del flow `negociacion`**, reutilizando el mismo pipeline contractual.

### Paso 1: crear carpeta de contexto

Clona `backend/negociacion/contexts/sala_reuniones` como plantilla:

- `manifest.json`
- `prompts/*.txt`
- `assets/*.json`
- `evaluation/*`
- opcional: `prompt_io_mapping.json`
- opcional: `presentation/presentation_config.json`

### Paso 2: editar `manifest.json`

Define:

- `flow_id` (normalmente `negociacion`),
- `context_id` único,
- `public_slug` único,
- `context_version`,
- bundle dirs correctos.

Si `manifest` no parsea o faltan archivos requeridos, el resolver no lo listará.

### Paso 3: preparar assets mínimos obligatorios

Asegura existencia y forma compatible de:

- `persona.json`
- `negotiation_brief.json`
- `phase_cards.json`
- `phase_classifier_card.json`

El parser de brief se valida con tests de assets.

### Paso 4: prompts por nodo

Incluye al menos:

- `summarizer_prompt.txt`
- `phase_classifier_prompt.txt`
- `planner_prompt.txt`
- `executor_prompt.txt`

Recuerda: los nodos esperan JSON estricto según sus modelos pydantic.

### Paso 5: (opcional) mapping prompt IO

Si necesitas nombres de campos distintos o payloads más UX-friendly para prompts:

- agrega `prompt_io_mapping.json` v1 o v2,
- valida que no ocultes campos required de output.

### Paso 6: presentación contextual

Si la UI debe cambiar (avatar/fondo/calibración/voz), agrega:

- `presentation/presentation_config.json`.

El resolver hará merge profundo con defaults.

### Paso 7: validar rutas públicas

Con `public_slug` listo, la app expone:

- `/interfaz_usuario/{public_slug}`.

Y el bootstrap puede recibir `public_slug` para resolver `context_id` automáticamente.

### Paso 8: pruebas mínimas recomendadas

Corre, como mínimo:

- `backend/tests/test_negotiation_context_assets_schema.py`
- `backend/tests/test_turn_context_contract.py`
- `backend/tests/test_api_negociar_context_contract.py`
- `backend/tests/test_sala_reuniones_prompt_io_mapping.py` (como referencia para mapping)

### Paso 9: validación e2e funcional

- bootstrap sesión con el nuevo contexto,
- ejecuta varios turnos por `interfaz_usuario` y `optimizador`,
- revisa en traces que `context_meta` y `_entry_contract` reflejen el contexto esperado,
- comprueba que no existan `context_mismatch` ni degradaciones de guardrails.

---

## 9) Errores típicos al crear contexto nuevo

1. **Manifest correcto, assets incompletos** → contexto no oficial (no aparece/lista).
2. **Cambio de contexto dentro de sesión existente** → conflicto de sesión.
3. **`config.context_id` ≠ `turn_context.effective_context_id`** → falla pre-ejecución.
4. **`prompts_dir` no pertenece al contexto declarado** → `InvalidConfigContextError`.
5. **Mapping oculta required output fields** → `PromptIOMappingError`.

---

## 10) Regla de oro para developers

Si quieres un flujo nuevo “de verdad” sin deuda:

1. crea contexto oficial completo,
2. ejecútalo siempre vía `execute_turn_with_contract`,
3. no saltes `ensure_session_context` ni `validate_turn_context_pre_execution`,
4. usa tests de contrato/contexto como puerta de merge.

Con eso mantienes consistencia entre UI pública, optimizador, legacy, trazas y runtime cognitivo.
