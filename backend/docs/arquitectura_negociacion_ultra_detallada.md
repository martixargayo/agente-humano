# Sistema de negociación: documento ultra detallado

## 1) Qué es este sistema y qué problema resuelve

El módulo de **negociación** implementa un flujo cognitivo multi-nodo para responder turnos de usuario en un contexto de compraventa (caso Mustang), manteniendo estado persistente, reglas de seguridad y trazabilidad de cada decisión.

A nivel práctico:

1. Recibe `user_id`, `session_id`, `message` por API canónica (`/api/negotiation/turn`).
2. Carga (o crea) el estado canónico de negociación de esa sesión.
3. Ejecuta nodos especializados:
   - `memory`
   - `phase_classifier`
   - `planner`
   - `executor`
4. Aplica guardarraíles de entrada/salida.
5. Persiste estado actualizado + trazas.
6. Devuelve `reply` y bandera `finish_button_armed`.

---

## 2) Punto de entrada y contrato HTTP (input/output externos)

### 2.1 Endpoint

El endpoint principal de este dominio es:

- `POST /api/negotiation/turn` (canónico)
- `POST /negociar` (legacy wrapper)

Recibe un `ChatRequest` con:

- `user_id: str`
- `session_id: str`
- `message: str`

Y devuelve un `ChatResponse` con:

- `reply: str`
- `finish_button_armed: bool`

### 2.2 Flujo de llamada

Canónico (`/api/negotiation/turn`):

1. valida `channel` + `execution_profile` (regla dura: avatar solo `canonical_negotiation`),
2. resuelve sesión de negociación namespaced (avatar => `neg::`),
3. llama `run_negotiation_turn_canonical(...)`,
4. responde con `reply` + metadata canónica (`effective_config_hash`, `prompts_dir_effective`, etc.).

Legacy (`/negociar`): wrapper fino al endpoint/servicio canónico con `channel=avatar` + `execution_profile=canonical_negotiation`.

Esto significa que el cliente no necesita conocer la complejidad interna (nodos, prompts, guardrails, threading): consume una interfaz mínima de chat.

---

## 3) Capa de orquestación: quién llama a quién

La ruta de ejecución es:

1. Adaptador (`/api/negotiation/turn`, `/negociar`, optimizador)
2. `run_negotiation_turn_canonical(...)` (en `orchestration/turn_service.py`)
3. `run_negotiation_cognitive_turn_detailed(...)` (en `orchestration/flow_config.py`) ejecuta el turno completo

`run_negotiation_cognitive_turn` es el **core real**: ahí se construyen inputs de nodos, se formatean prompts, se invoca OpenAI con Structured Outputs, se aplican guardarraíles, se persiste estado y se arma la traza.

---

## 4) Estado canónico (la “fuente de verdad”)

El sistema usa `CanonicalState` como contrato fuerte de dominio (Pydantic, `extra="forbid"`) para minimizar deriva estructural.

### 4.1 Bloques del `CanonicalState`

- `session`: metadatos de sesión (`session_id`, `user_id`, timestamps)
- `openai_thread`: estado de threading OpenAI (`thread_mode`, `conversation_id`, `previous_response_id`)
- `persona`: dos capas
  - `policy` (disciplina/criterio privado)
  - `expressive` (voz/estilo en escena)
- `negotiation_brief`: marco estratégico base del caso
- `memory_episodic`: recuerdos tipo evento (offer, blocker, etc.)
- `memory_working`: foco operativo del turno (`current_topic`, `pending_question`, `last_turn_summary`)
- `negotiation_state`: snapshot táctico (ofertas vigentes, bloqueos, estancamiento, etc.)
- `planner_state`: fase actual/anterior + objetivo de turno + historial de fases
- `scene_state`: encuadre situacional (copresencia, encuentro en curso)
- `ui_state`: estado de interfaz (`finish_button_armed`)
- `trace`: últimos estados de ejecución (fallbacks, rechazos, etc.)

### 4.2 Carga y persistencia

La clase `StateRepository` se encarga de:

- `load_state(...)`: valida y reconstruye `CanonicalState` desde `world_state[memory_key]`
- `save_state(...)`: serializa de vuelta a `world_state`
- `load_recent_dialogue(...)` / `save_recent_dialogue(...)`
- `append_trace(...)`

Si la carga falla por shape inválido, hay fallback seguro a `build_default_canonical_state(...)`.

---

## 5) Inputs/Outputs internos por nodo (contratos de datos)

Todos los nodos trabajan con modelos Pydantic estrictos para garantizar I/O determinista.

### 5.1 Memory node

**Input**: `MemoryInput`

Incluye: `user_turn`, `recent_dialogue_short`, memoria actual, estado de escena y `trace_meta`.

**Output**: `MemoryOutput`

- `episodic_append`
- `working_memory_new`
- `negotiation_state`

Este nodo no responde al usuario; produce patch semántico de memoria + estado negociador.

### 5.2 Phase classifier node

**Input**: `PhaseClassifierInput`

Incluye fase previa, historial reciente de fases, card de clasificación y turnos recientes.

**Output**: `PhaseClassifierOutput`

- `current_phase` (enum `NegotiationPhase`)

Fases disponibles:

- `clima_humano`
- `descubrimiento_y_comprension`
- `propuesta_creativa`
- `concesiones_y_ajuste_final`
- `formalizacion_del_acuerdo`
- `abandono_de_la_negociacion`

### 5.3 Planner node

**Input**: `PlannerInput`

Incluye persona policy, negotiation brief, fase actual, `phase_card`, memoria seleccionada y estado operativo.

**Output**: `PlannerOutput`

Campos clave:

- `status`: `plan | clarify | refuse`
- `turn_goal`
- `decision`: `hold | ask | counter | accept | reject | close`
- `content_plan` (`must_include`, `must_avoid`)
- `limits` (máx frases, máx preguntas, topic shift, disclosure)
- `memory_targets`
- `done_criteria`

El planner decide táctica; no redacta mensaje final humano.

### 5.4 Executor node

**Input**: `ExecutorInput`

Incluye `planner_output`, `persona_expressive`, límites de respuesta y memoria de referencia.

**Output**: `ExecutorOutput`

- `status`: `deliver | clarify | refuse`
- `spoken_text`
- `memory_used`
- `refusal_reason`

Este es el único nodo que produce la respuesta final al usuario.

---

## 6) Prompts: dónde viven y cómo se usan

Los prompts están en `backend/negociacion/prompts/`:

- `summarizer_prompt.txt` → prompt del nodo memory
- `phase_classifier_prompt.txt`
- `planner_prompt.txt`
- `executor_prompt.txt`
- `phase_classifier_card.json`
- `phase_cards.json`
- `persona.json`
- `negotiation_brief.json`

La orquestación carga prompts con `_read_text(...)` y usa fallbacks por defecto si falta archivo.

### 6.1 Estructura de mensajes enviados al modelo

Cada llamada usa dos mensajes:

1. `role=developer` con el prompt del nodo
2. `role=user` con `<task_input> ... JSON input ... </task_input>`

Se fuerza “solo JSON válido” del schema esperado (`MemoryOutput`, `PlannerOutput`, etc.).

### 6.2 Congelación de artefactos de prompt (observabilidad)

Antes de llamar al modelo, `freeze_prompt_artifacts(...)` guarda snapshot:

- prompt developer renderizado
- user prompt renderizado
- payload JSON exacto
- hashes (`developer_prompt_hash`, `user_prompt_hash`, `payload_hash`)
- metadata de versión/schema/modelo/threading

Esto permite auditoría reproducible por turno.

---

## 7) Secuencia exacta de ejecución por turno

Dentro de `run_negotiation_cognitive_turn(...)`:

1. Verifica compatibilidad SDK (`check_openai_sdk_compatibility`).
2. Carga estado canónico + diálogo reciente.
3. Construye `user_turn` normalizado.
4. Carga prompts de nodos.
5. Ejecuta guardarraíl de entrada.
6. Si `block` de input guardrail:
   - responde bloqueo,
   - no ejecuta camino normal de nodos.
7. Si no bloquea:
   - refresca contexto de threading OpenAI,
   - construye `memory_input` y `phase_input`,
   - ejecuta `memory` y `phase_classifier` **en paralelo**,
   - aplica outputs al estado,
   - evalúa reglas de `finish_button`,
   - construye `planner_input` y llama planner,
   - aplica planner al estado,
   - construye `executor_input` y llama executor,
   - ejecuta output guardrails (pueden reescribir/forzar estado de salida).
8. Emite reply final (`spoken_text`) al historial.
9. Construye `TurnTrace` completo con latencias, fuentes, guardrails, IDs de threading, etc.
10. Persiste todo y devuelve respuesta.

---

## 8) Paralelismo, threading y contextos OpenAI

El sistema define políticas por nodo:

- `memory` y `phase_classifier`: `stateless_parallel`
- `planner` y `executor`: `stateful_sequential`

Implicación:

- Memory y phase corren en paralelo con `ThreadPoolExecutor(max_workers=2)` y sin compartir contexto conversacional mutable.
- Planner y executor sí usan contexto secuencial (`conversation` o `previous_response_id`) según `thread_mode`.

Se actualiza `conversation_id` / `previous_response_id` después de cada respuesta cuando aplica.

---

## 9) Guardarraíles (input/output + moderación)

La política se arma con `build_guardrails_policy(...)` y flags de config:

- `feature_input_guardrails`
- `feature_output_guardrails`
- `feature_moderation`

### 9.1 Input guardrails

`run_input_guardrails(...)` puede devolver:

- `allow`
- `soft_restrict`
- `block`

En v1, `soft_restrict` es marcador de riesgo pero **no** corta ejecución normal.

### 9.2 Output guardrails

`run_output_guardrails(...)` recibe `executor_output + planner_output + user_turn` y puede:

- mantener salida,
- reescribir texto,
- cambiar status (`deliver/clarify/refuse`),
- adjuntar razones y evidencia de aplicación.

Todo queda registrado en traza (`status_before/after`, `rewrite_applied`, reglas observadas/aplicadas, flags de moderación).

---

## 10) Fallbacks y resiliencia

Hay fallback explícito por nodo cuando falla modelo, parseo o hay refusal:

- `_memory_fallback(...)`
- `_phase_classifier_fallback(...)`
- `_planner_fallback(...)`
- `_executor_fallback(...)`

Además:

- si falta `OPENAI_API_KEY`, el cliente se desactiva y se usa modo fallback,
- `StateRepository.load_state` cae a estado default si hay invalidación,
- lectura de prompts/cards tiene fallback seguro.

Resultado: el sistema prioriza continuidad de servicio, aunque con menor calidad estratégica cuando opera en fallback.

---

## 11) Trazas y evaluabilidad

Si `feature_traces=True`, cada turno guarda `TurnTrace` en `world_state`.

La traza incluye:

- metadatos temporales y latencia total
- IDs de thread antes/después
- reply final + excerpt
- señales de guardarraíles
- modelo/prompt/schema versionados
- logs por nodo
- fuente de salida (`model`, `fallback`, `refusal`, etc.)
- calificaciones stub de alineamiento planner↔executor

Esto alimenta los runners de evals en `backend/negociacion/evals/runners/`.

---

## 12) Configuración del flujo (modelos y flags)

`NEGOTIATION_FLOW_DETAILS` fija defaults, por ejemplo:

- modelos:
  - memory: `gpt-5-nano`
  - phase_classifier: `gpt-5-nano`
  - planner: `o4-mini`
  - executor: `gpt-5-nano`
- `reasoning_effort_planner="medium"`
- `thread_mode_default=conversation`
- `max_recent_messages=12`
- `max_executor_recent_turns=4`
- features de guardrails/traces/evals habilitadas

`build_negotiation_pipeline_config()` transforma eso en `NegotiationTurnConfig`.

---

## 13) Semántica funcional resumida (en una frase por nodo)

- **memory**: “Qué ha pasado y qué debo recordar/actualizar para operar bien el próximo turno”.
- **phase_classifier**: “En qué fase de negociación estamos ahora mismo”.
- **planner**: “Qué movimiento táctico conviene hacer ahora, con límites concretos”.
- **executor**: “Cómo decir ese movimiento al usuario en lenguaje humano y controlado”.

---

## 14) Dónde tocar si quieres cambiar comportamiento

- Cambiar modelos/flags/orden lógico de configuración:
  - `backend/negociacion/orchestration/flow_config.py`
- Cambiar contratos de input/output:
  - `backend/negociacion/nodes/*.py`
- Cambiar personalidad o marco del caso:
  - `backend/negociacion/prompts/persona.json`
  - `backend/negociacion/prompts/negotiation_brief.json`
- Cambiar guía por fase:
  - `backend/negociacion/prompts/phase_cards.json`
  - `backend/negociacion/prompts/phase_classifier_card.json`
- Cambiar restricciones narrativas de cada nodo:
  - `backend/negociacion/prompts/*_prompt.txt`
- Cambiar estado persistente del dominio:
  - `backend/negociacion/state/canonical_state.py`

---

## 15) Mapa mental final (ultra corto)

**Input externo** → `/api/negotiation/turn` (canónico) → `run_negotiation_turn_canonical` → `run_negotiation_cognitive_turn_detailed` → guardrail entrada → (memory || phase) → planner → executor → guardrail salida → persistir estado+traza → **Output canónico (`reply`, `effective_config_hash`, `finish_button_armed`, ...)**.

Ese es el esqueleto completo del sistema en producción actual.
