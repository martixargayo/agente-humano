# 02 · Fase 1 — Esqueleto y contratos base

## 1) Alcance de la fase

### Hecho observado

`negociacion` ya tiene patrones estables para:
- resolver de contexto (`backend/negociacion/contexts/resolver.py`),
- binding de sesión (`backend/negociacion/contexts/session_binding.py`),
- contrato de turn context (`backend/negociacion/orchestration/turn_execution_context.py`, `turn_context_validator.py`, `turn_contract.py`),
- estado canónico (`backend/negociacion/state/canonical_state.py`).

### Propuesta

Construir equivalente scoped a `conversacion_simple`, duplicando controladamente lo esencial y evitando modificar runtime existente.

### Decisión operativa

Fase 1 **no ejecuta turnos con LLM**, solo deja cimientos estructurales y contractuales.


## Decisiones cerradas de alcance Fase 1

1. **prompt_io_mapping:** en Fase 1 no se duplica motor; se reutiliza/reexporta el existente sin activación nueva específica del runtime.
2. **turn_contract compartido:** en Fase 1 no se toca `backend/negociacion/orchestration/turn_contract.py`.
3. **context errors:** taxonomía propia en namespace `conversacion_simple` sin modificar errores operativos de `negociacion`.
4. **presentation:** no hay capa de presentation propia integrada en Fase 1; solo estructura de assets de contexto.
5. **naming congelado:** se congela naming base: `backend/conversacion_simple/`, `ConversationSimpleCanonicalState`, `build_default_conversation_simple_canonical_state`, `build_conversacion_simple_turn_context`, `ConversationSimpleTurnConfig`, `conversation_simple_canonical`, `conversation_simple_canonical_recent_dialogue`, `conversation_simple_canonical_traces`.

---

## 2) Qué se hará

1. Crear paquete `backend/conversacion_simple/`.
2. Crear submódulos:
   - `contexts/`
   - `state/`
   - `orchestration/`
   - `services/` (solo factories/context helpers en esta fase)
3. Definir modelos base:
   - `BoundConversationSimpleContext`
   - `ResolvedConversationSimpleContext`
   - `ConversationSimpleCanonicalState`
4. Definir llaves de persistencia del flow:
   - `conversation_simple_canonical`
   - `conversation_simple_canonical_recent_dialogue`
   - `conversation_simple_canonical_traces`
5. Crear contextos oficiales iniciales vacíos/plantilla:
   - `backend/conversacion_simple/contexts/baseline/`
   - `backend/conversacion_simple/contexts/negociacion_sala_reuniones/`
6. Resolver/binding/public mapping equivalentes para el nuevo flow.
7. Crear `build_conversacion_simple_turn_context(...)` en factoría de servicios.
8. Tests de contrato/contexts/estado base.

---

## 3) Archivos nuevos a crear (propuestos)

## 3.1 Núcleo paquete

- `backend/conversacion_simple/__init__.py`

## 3.2 Contextos

- `backend/conversacion_simple/contexts/__init__.py`
- `backend/conversacion_simple/contexts/models.py`
- `backend/conversacion_simple/contexts/resolver.py`
- `backend/conversacion_simple/contexts/session_binding.py`
- `backend/conversacion_simple/contexts/public_mapping.py`
- `backend/conversacion_simple/contexts/prompt_io_mapping.py` *(si se decide duplicar motor; alternativa: reexport del actual en Fase 1)*
- `backend/conversacion_simple/contexts/baseline/manifest.json`
- `backend/conversacion_simple/contexts/baseline/prompts/brain_prompt.txt`
- `backend/conversacion_simple/contexts/baseline/assets/persona.json`
- `backend/conversacion_simple/contexts/baseline/assets/conversation_brief.json`
- `backend/conversacion_simple/contexts/baseline/assets/phase_cards.json`
- `backend/conversacion_simple/contexts/baseline/presentation/presentation_config.json`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/...` *(mismos archivos, equivalentes en esta fase)*

## 3.3 Estado

- `backend/conversacion_simple/state/__init__.py`
- `backend/conversacion_simple/state/shared_types.py`
- `backend/conversacion_simple/state/canonical_state.py`

## 3.4 Orquestación (base sin runtime LLM)

- `backend/conversacion_simple/orchestration/__init__.py`
- `backend/conversacion_simple/orchestration/flow_config.py` *(solo config/modelos base en Fase 1)*
- `backend/conversacion_simple/orchestration/context_errors.py` *(si se decide separar namespace; alternativa: reusar `negociacion`)*
- `backend/conversacion_simple/orchestration/turn_execution_context.py` *(o reutilizar tipo actual según decisión de compatibilidad)*

## 3.5 Servicios base

- `backend/conversacion_simple/services/__init__.py`
- `backend/conversacion_simple/services/turn_context_factory.py`

## 3.6 Tests

- `backend/tests/test_conversacion_simple_context_resolution.py`
- `backend/tests/test_conversacion_simple_context_binding.py`
- `backend/tests/test_conversacion_simple_context_contract.py`
- `backend/tests/test_conversacion_simple_assets_schema.py`
- `backend/tests/test_conversacion_simple_canonical_state_defaults.py`

---

## 4) Archivos existentes a modificar (propuestos)

1. `backend/tests/...` índice o utilidades comunes si requieren descubrimiento del nuevo flow.
2. `backend/README.md` *(solo si se mantiene inventario de flujos)*.

> En Fase 1 evitar tocar `backend/api/app.py`, `interfaz_usuario/services.py`, `negociacion/optimizador/services.py`.

---

## 5) Código que NO se tocará en Fase 1

1. `backend/negociacion/orchestration/flow_config.py` (runtime actual intacto).
2. `backend/interfaz_usuario/services.py` (sin integración aún).
3. `backend/negociacion/optimizador/services.py` (sin integración aún).
4. `backend/api/app.py` rutas de producción existentes.
5. Cualquier lógica de compresión diferida.

---

## 6) Funciones/clases concretas propuestas

## Contextos

- `resolve_default_conversacion_simple_context()`
- `resolve_conversacion_simple_context(context_id: str | None)`
- `list_official_conversacion_simple_contexts()`
- `resolve_conversacion_simple_context_from_public_slug(public_slug: str)`
- `ensure_conversacion_simple_session_context(state, requested_context_id=None)`
- `read_bound_conversacion_simple_context_from_session(state)`

## Estado

- `ConversationSimpleCanonicalState`
- `build_default_conversation_simple_canonical_state(...)`
- `parse_conversation_simple_brief_payload(...)`

## Orquestación base

- `ConversationSimpleTurnConfig` (pydantic)
- `build_conversacion_simple_pipeline_config(...)` *(sin ejecución LLM todavía)*

## Servicios

- `build_conversacion_simple_turn_context(...)`

---

## 7) Cómo será cada modificación (concreto)

1. **Resolver de contextos**
   - crear `conversacion_simple/contexts/resolver.py` replicando patrón de `negociacion/contexts/resolver.py` con defaults:
     - `flow_id = "conversacion_simple"`
     - contextos iniciales `baseline` y `negociacion_sala_reuniones`.
2. **Session binding**
   - crear key propia de world_state:
     - `CONVERSACION_SIMPLE_CONTEXT_WORLD_STATE_KEY = "conversacion_simple_context"`.
3. **Canonical state**
   - crear estado base propio con `memory_working`, `memory_episodic`, `conversation_state`, `trace`, `ui_state`.
4. **Turn context factory**
   - crear `build_conversacion_simple_turn_context` siguiendo contrato de `TurnExecutionContext` actual.
5. **Config base**
   - crear builder de config con `memory_key = "conversation_simple_canonical"`.

---

## 8) Riesgos de Fase 1

1. Divergencia innecesaria de contratos desde el inicio.
2. Over-engineering del estado antes de runtime real.
3. Duplicación inconsistente de assets entre contextos iniciales.

### Mitigación

- tests de equivalencia entre `baseline` y `negociacion_sala_reuniones`.
- mantener `extra="forbid"` en modelos pydantic base.
- scope estricto: no tocar surfaces/runtime.

---

## 9) Tests de la fase

1. Resolver lista ambos contextos oficiales.
2. Resolver falla en context_id inválido.
3. Public slug resuelve correctamente.
4. Session binding bloquea conflicto de contexto.
5. Canonical state default instancia sin campos faltantes.
6. Assets schema parsea en ambos contextos.

---

## 10) Criterio de Done de Fase 1

- Todos los tests nuevos de Fase 1 en verde.
- No hay cambios funcionales en endpoints ni runtime `negociacion`.
- Existe estructura completa de `backend/conversacion_simple` con contratos base y contextos iniciales equivalentes.
- PR acotada: solo esqueleto + contratos + tests de base.
