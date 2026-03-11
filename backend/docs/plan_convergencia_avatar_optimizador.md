# Plan de convergencia total: AVATAR negociación = OPTIMIZADOR canónico

## 0) Estado actual verificado en código (baseline)

Hallazgos comprobados en este repo:

1. **Avatar y optimizador no entran por la misma API de negociación**.
   - Avatar (modo negociación) llama `POST /negociar` o `POST /chat` según modo en frontend. (`fetchAgentReply`) .
   - Optimizador envía mensajes por `POST /api/optimizador/sandbox/turn` (`sendChat`) .

2. **Avatar usa sesión fija hardcodeada**: `user_id='web_user'`, `session_id='sesion_demo'`.
   - Esto no es equivalente semánticamente al flujo del optimizador, que selecciona sesión activa desde la UI y puede clonar/new conversation.

3. **El endpoint `/negociar` va directo a `run_negotiation_agent`** (pipeline base sin capa optimizador).
   - El optimizador usa `services.run_sandbox_turn(...)`, que además resuelve y aplica overrides, metadata `_optimizador`, versionado y contexto de conversación.

4. **El optimizador hoy añade semántica extra de ejecución** (overrides prompt/config/contextual, `workspace_version`, `mode`, `versioning`) que no existe en `/negociar`.

5. **Sí existe un core negociador común real**: `run_negotiation_cognitive_turn(...)`.
   - `/negociar` llega por `run_negotiation_agent(...)`.
   - Optimizador también termina en `run_negotiation_cognitive_turn(...)` desde `run_sandbox_turn(...)`.

Conclusión del baseline: actualmente hay **misma base cognitiva**, pero **dos entrypoints semánticos distintos** para negociación.

---

## 1) Recomendación arquitectónica final

### Opción elegida: **Opción 1 — Un único entrypoint canónico**

Recomendación concreta para este repo:

- Crear un servicio canónico único de negociación (p. ej. `run_negotiation_turn_canonical(...)`) en backend.
- Hacer que **avatar-negociación** y **optimizador** llamen ambos a ese servicio.
- Mantener diferencias solo en adaptador UI/API (shape de request/response), no en semántica de ejecución.

### Por qué Opción 1 y no Opción 2

- Opción 2 (avatar llamando directo al endpoint del optimizador) acopla al avatar con conceptos de laboratorio (`optimizer_session_id`, `scope_turn_id`, `repeat_from_turn_id`, modos sandbox/mirror).
- Opción 1 permite separar:
  - **Core canónico de ejecución** (idéntico para avatar y optimizador),
  - **Capacidades experimentales del optimizador** (overrides/versionado) como decoradores opcionales.

### Qué significa exactamente aquí “avatar = réplica del optimizador”

En este repo significa:

1. Mismo estado inicial de negociación (`CanonicalState` + `ThreadMode` + `memory_key`).
2. Mismo `NegotiationTurnConfig` efectivo (incluido `prompts_dir`, modelos, flags guardrails, límites).
3. Misma construcción de inputs (`MemoryInput`, `PhaseClassifierInput`, `PlannerInput`, `ExecutorInput`).
4. Mismo threading OpenAI (`conversation_id` / `previous_response_id` lifecycle).
5. Misma ejecución guardrails + misma persistencia de trazas.
6. Diferencias permitidas solo en presentación UI y en metadata auxiliar no usada por el core.

---

## 2) Mapa de cambios concretos

> Formato: archivo · función/módulo · cambio · tipo · impacto · prioridad

### A. Backend canónico de ejecución

1. `backend/negociacion/orchestration/` (nuevo `turn_service.py` o similar)
   - **Crear** `run_negotiation_turn_canonical(...)`.
   - Recibe: `state`, `message`, `config`, `execution_profile`, `applied_overrides_meta` opcional.
   - Internamente llama a `run_negotiation_cognitive_turn(...)` y devuelve:
     - `reply`
     - `turn_trace` (último)
     - `effective_config` serializada
     - `effective_config_hash`
   - **Tipo:** refactor estructural.
   - **Impacto:** alto (single source of truth).
   - **Prioridad:** P0.

2. `backend/negociacion/pipeline.py`
   - `run_negotiation_agent(...)` pasa a ser thin-wrapper del nuevo servicio canónico.
   - **Tipo:** refactor.
   - **Impacto:** medio.
   - **Prioridad:** P0.

3. `backend/negociacion/optimizador/services.py`
   - `run_sandbox_turn(...)` deja de invocar directamente `run_negotiation_cognitive_turn(...)`.
   - Debe llamar al servicio canónico con `execution_profile='optimizador'` + overrides resueltos.
   - `_optimizador` metadata permanece, pero sin bifurcar semántica del turno.
   - **Tipo:** refactor.
   - **Impacto:** alto.
   - **Prioridad:** P0.

### B. API y contratos de entrada

4. `backend/api/app.py`
   - `/negociar` debe invocar el servicio canónico (no wrapper paralelo).
   - Añadir endpoint canónico interno (si conviene) para negociación (`/api/negotiation/turn`) y dejar `/negociar` como compat.
   - **Tipo:** refactor + compat.
   - **Impacto:** alto.
   - **Prioridad:** P0.

5. `backend/negociacion/optimizador/__init__.py`
   - `/sandbox/turn` mantiene contrato UI optimizador pero delega al mismo servicio canónico.
   - **Tipo:** refactor.
   - **Impacto:** alto.
   - **Prioridad:** P0.

### C. Avatar (eliminar divergencias)

6. `backend/avatar_app/app.js`
   - Eliminar sesión fija (`web_user`/`sesion_demo`).
   - Introducir session bootstrap compartido con optimizador o policy única de `session_id` generada por UI.
   - En modo negociación, llamar endpoint canónico unificado (mismo shape lógico que optimizador-negociación).
   - **Tipo:** refactor funcional.
   - **Impacto:** muy alto.
   - **Prioridad:** P0.

7. `backend/avatar_app/app.js` (modo chat estándar)
   - Opción recomendada: **separarlo completamente** de negociación con namespace de sesión distinto (`chat::<id>` vs `neg::<id>`) y sin compartir estado/thread.
   - Alternativa agresiva: deshabilitar chat estándar en avatar.
   - **Tipo:** simplificación de arquitectura.
   - **Impacto:** alto.
   - **Prioridad:** P1.

### D. Config efectiva y observabilidad

8. `backend/negociacion/orchestration/flow_config.py` + `backend/negociacion/traces/models.py`
   - Añadir en traza: `effective_config`, `effective_config_hash`, `execution_profile`, `prompts_dir_effective`.
   - Hoy esto no está explícito en traza (hipótesis confirmada por inspección de `TurnTrace` y `services.run_sandbox_turn`).
   - **Tipo:** extensión de trazabilidad.
   - **Impacto:** alto para pruebas de identidad.
   - **Prioridad:** P0.

9. `backend/negociacion/optimizador/services.py`
   - Persistir `effective_config_hash` también en `_optimizador` para comparativas A/B del optimizador.
   - **Tipo:** extensión.
   - **Impacto:** medio.
   - **Prioridad:** P1.

### E. Legacy cleanup

10. `backend/api/app.py` + frontend
    - Mantener `/negociar` y `/api/optimizador/sandbox/turn` como adaptadores de compatibilidad, pero ambos delegan al mismo servicio canónico.
    - Dejar marcado deprecado cualquier camino que construya config/threading por fuera.
    - **Tipo:** deprecación controlada.
    - **Impacto:** medio.
    - **Prioridad:** P1.

---

## 3) Plan de implementación por fases

## Fase 1 — Definir flujo canónico único

**Objetivo**
- Tener un solo entrypoint interno para ejecutar turnos de negociación.

**Archivos**
- `backend/negociacion/orchestration/turn_service.py` (nuevo)
- `backend/negociacion/pipeline.py`
- `backend/negociacion/optimizador/services.py`

**Cambios**
- Crear `run_negotiation_turn_canonical`.
- Migrar `run_negotiation_agent` y `run_sandbox_turn` a ese servicio.

**Riesgos**
- Romper metadata `_optimizador` si no se injerta después de ejecutar turno.

**Criterio de aceptación**
- Avatar-negociación y optimizador ejecutan la misma función canónica por turnos.

## Fase 2 — Colapsar semántica de sesión y reset

**Objetivo**
- Política única de sesión para negociación, sin hardcodes del avatar.

**Archivos**
- `backend/avatar_app/app.js`
- `backend/negociacion/optimizador/session_bridge.py`
- `backend/api/app.py`

**Cambios**
- Reemplazar `web_user/sesion_demo` por sesión real seleccionable/generada.
- Definir `new_conversation` único: nueva sesión limpia + `openai_thread` reiniciado.
- Estandarizar reset para avatar y optimizador.

**Riesgos**
- UX del avatar puede requerir persistencia local de IDs.

**Criterio de aceptación**
- Mismo estado inicial y mismo comportamiento de reset en ambos canales.

## Fase 3 — Bloquear config efectiva

**Objetivo**
- Garantizar que negociación-avatar use mismo profile/config/prompts que optimizador (salvo overrides explícitos del optimizador).

**Archivos**
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/optimizador/experiments_bridge.py`
- `backend/api/app.py`

**Cambios**
- Introducir `execution_profile` explícito.
- Registrar `effective_config` + hash.
- En avatar-negociación, deshabilitar overrides (o fijar mirror estricto).

**Riesgos**
- Cambios en schema de traza.

**Criterio de aceptación**
- `effective_config_hash` igual entre avatar-negociación y optimizador para el mismo caso.

## Fase 4 — Unificar observabilidad

**Objetivo**
- Trazas comparables 1:1 para demostrar identidad funcional.

**Archivos**
- `backend/negociacion/traces/models.py`
- `backend/negociacion/traces/builders.py`
- `backend/negociacion/optimizador/services.py`

**Cambios**
- Incluir hashes y payload snapshots por nodo en formato estable.
- Exponer endpoint de comparación canónica (no solo `_optimizador`).

**Riesgos**
- Aumentar tamaño de traza.

**Criterio de aceptación**
- Se puede comparar turno A/B y detectar divergencia exacta por nodo.

## Fase 5 — Eliminar rutas divergentes legacy

**Objetivo**
- No dejar caminos negociadores paralelos.

**Archivos**
- `backend/api/app.py`
- `backend/avatar_app/app.js`

**Cambios**
- Mantener rutas legacy solo como proxy al canónico.
- Desactivar cualquier lógica avatar-specific que altere negociación.

**Riesgos**
- Integraciones antiguas consumiendo `/negociar` o `/chat` desde avatar.

**Criterio de aceptación**
- Cualquier request de negociación termina en el mismo servicio canónico.

## Fase 6 — Pruebas de identidad/paridad

**Objetivo**
- Evidencia automatizada de identidad semántica.

**Archivos**
- nuevos tests en `backend/tests/` (ver sección 5)

**Cambios**
- Suite de paridad estricta avatar vs optimizador.

**Riesgos**
- Flakiness si se usa llamada real al modelo sin mocks.

**Criterio de aceptación**
- Tests verdes comparando inputs/outputs/traces/hash/threading.

---

## 4) Decisiones de compatibilidad

### 4.1 Modo chat estándar en avatar

Recomendación:

- **No mezclar chat estándar con negociación**.
- Si se conserva chat: aislar totalmente (`session_id`/`memory_key`/threading separados).
- Si hay conflicto de producto, eliminarlo del avatar para simplificar.

### 4.2 Endpoints legacy

- Mantener temporalmente:
  - `/negociar` (compat)
  - `/api/optimizador/sandbox/turn` (UI optimizador)
- Ambos como adaptadores al servicio canónico.

### 4.3 Sesiones existentes

- No requiere migración destructiva global.
- Sí conviene:
  - Namespace claro para nuevas sesiones (`neg::*`, `chat::*`).
  - Para sesiones viejas del avatar con hardcode, ofrecer “reset/new conversation” y dejar que expiren.

### 4.4 Migración

- **Hipótesis**: no hace falta migración de `CanonicalState` si no se cambia schema duro.
- Si se agrega `effective_config_hash` en traza, es aditivo y backward-compatible.

---

## 5) Plan de validación (pruebas de identidad real)

## 5.1 Unit tests

1. `test_avatar_and_optimizer_use_same_canonical_entrypoint`
   - Verifica que ambos adapters llaman `run_negotiation_turn_canonical`.

2. `test_same_effective_config_hash_for_same_case`
   - Mismo input/session/prompts -> mismo `effective_config_hash`.

3. `test_avatar_negotiation_disallows_optimizer_overrides`
   - Avatar-negociación ignora/deniega overrides.

## 5.2 Integration tests (mock structured calls)

Con monkeypatch de `_call_structured` y reloj controlado:

1. Ejecutar turno por adapter avatar-negociación.
2. Ejecutar turno por adapter optimizador (modo mirror, sin overrides).
3. Comparar igualdad exacta de:
   - `memory_input` (`prompt_artifacts.input_payload_json` nodo memory)
   - `phase_input`
   - `planner_input`
   - `executor_input`
   - `planner_output`
   - `executor_output_before_guardrail`
   - `final_reply_text`
   - `effective_config_hash`
   - `threading` (`conversation_id_before/after`, `previous_response_id_before/after`)

## 5.3 Golden traces

- Guardar fixtures de trazas canónicas para casos clave:
  - saludo inicial
  - discovery
  - counteroffer
  - hard stalemate
  - cierre/abandono
- Re-ejecutar avatar vs optimizador y validar equivalencia de campos críticos.

## 5.4 Validación de threading

- Caso `ThreadMode.conversation`:
  - IDs de conversación evolucionan igual en ambos canales.
- Caso `ThreadMode.previous_response_id`:
  - chain de `previous_response_id` idéntica.

---

## 6) Quick wins

### Quick wins (alto impacto / bajo esfuerzo)

1. **Eliminar hardcode de sesión en avatar** (`web_user` / `sesion_demo`).
2. **Forzar que avatar-negociación use el mismo endpoint interno que optimizador-mirror sin overrides**.
3. **Bloquear modo chat compartido con negociación** (separar sesión namespace ya).
4. **Exponer `effective_config_hash` en respuesta/trace**.

### Cambios estructurales necesarios para cerrarlo bien

1. Crear servicio canónico único de turnos.
2. Unificar semántica de reset/new conversation.
3. Consolidar observabilidad comparable (payload/hash/threading) como contrato estable.
4. Deprecar rutas divergentes que hoy construyen semántica distinta.

---

## 7) Partes del avatar que deben eliminarse/desactivarse/redirigirse (respuesta explícita B)

1. **Sesión fija del avatar** (`web_user`, `sesion_demo`): eliminar.
2. **Bifurcación `/chat` vs `/negociar` en avatar para modo negociación**: redirigir a un único adapter canónico de negociación.
3. **Cualquier reset local que no pase por política canónica de nueva conversación**: desactivar.
4. **Cualquier lógica avatar-specific que muta comportamiento negociador**: eliminar o mover a UI-only.
5. **Modo chat estándar**:
   - recomendado: separarlo completamente de negociación,
   - o eliminarlo del avatar si complica garantías de identidad.

---

## 8) Definición operativa de éxito (criterio final)

Se considera logrado cuando:

- Usuario entra al avatar, pulsa negociación,
- y ese turno ejecuta el **mismo servicio canónico** que optimizador,
- con misma config efectiva, mismo estado inicial/continuación, mismo threading y mismos guardrails,
- dejando trazas comparables donde la divergencia esperada sea solo metadata de UI/adaptador.

En esa condición, la arquitectura queda realmente como:

- **OPTIMIZADOR = sistema real (canónico)**
- **AVATAR = presentación de ese mismo sistema**



## Estado final implementado (cerrado)

- Servicio único real: `run_negotiation_turn_canonical(...)`.
- `channel` y `execution_profile` separados por contrato y validados en backend.
- Restricción dura: `channel=avatar` solo admite `canonical_negotiation`.
- Endpoint canónico: `POST /api/negotiation/turn`.
- `/negociar` queda como wrapper legacy fino al canónico.
- Optimizador ejecuta turnos por el mismo servicio canónico; la parte experimental queda como capa de overrides/versionado externa.
- Separación backend chat vs negociación por namespace de sesión (`chat::` y `neg::` para avatar).
- Reset/new conversation de negociación expuesto en backend (`/api/negotiation/session/reset`, `/api/negotiation/session/new_conversation`).
- Avatar negociación cableado al endpoint canónico y con acción visible de “Nueva negociación”.
