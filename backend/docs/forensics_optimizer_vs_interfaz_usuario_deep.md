# Forense de paridad: `optimizador` vs `interfaz_usuario`

## Alcance y metodología
- **Lectura estática** de rutas HTTP, servicios, contratos de entrada y runtime cognitivo.
- **Pruebas dinámicas reproducibles** con `TestClient` y runtime stubbeado para aislar diferencias de wrappers (sin ruido de modelo).
- **Evidencia** en JSON versionado: `backend/docs/forensics_optimizer_vs_interfaz_usuario_run.json`.

---

## Fase 1 — Mapa arquitectónico extremo a extremo

### A) Carril optimizador
1. **Endpoint**: `POST /api/optimizador/sandbox/turn`.  
2. **Handler**: `sandbox_turn(...)` en `backend/negociacion/optimizador/__init__.py`.  
3. **Schema request**: `SandboxTurnRequest` (incluye `optimizer_session_id`, `conversation_id`, `scope_turn_id`, `repeat_from_turn_id`).  
4. **Service principal**: `run_sandbox_turn(...)` en `backend/negociacion/optimizador/services.py`.
5. **Wrappers previos al runtime**:
   - Resuelve sesión con `get_session_state(...)`.
   - Construye config base `build_negotiation_pipeline_config(...)`.
   - Resuelve overrides por `optimizer_session_id/conversation_id/turn_id` (`experiments_bridge.resolve_entries`).
   - Aplica overrides de prompt/config/contextual (`experiments_bridge.apply_overrides`).
   - Aplica override contextual de persona directamente a canonical state (`_apply_contextual_state_overrides`).
   - Infiere flags de contrato (`clone_used`, `new_conversation`) desde `optimizador_sandbox_meta`.
6. **Llamada al runtime cognitivo**:
   - `execute_turn_with_contract(...)` con `entry_surface="optimizador"`, `optimizer_wrapper_used=True`, `overrides_applied=bool(resolved_entries)`.
7. **Persistencia y trazas**:
   - Runtime persiste en `negotiation_canonical`, `negotiation_canonical_traces`, etc.
   - Service añade bloque lateral `_optimizador` al último turn trace (session key, overrides efectivos, versionado A/B).
8. **Serialización respuesta**:
   - Devuelve `reply`, `turn`, `turn_title`, `effective_overrides`, `entry_contract`.

### B) Carril `interfaz_usuario`
1. **Endpoint**: `POST /api/interfaz_usuario/negociacion/turn`.
2. **Handler**: `negotiation_turn(...)` en `backend/interfaz_usuario/__init__.py`.
3. **Schema request**: `NegotiationTurnRequest` (`user_id`, `session_id`, `message`, `new_conversation`).
4. **Service principal**: `run_turn(...)` en `backend/interfaz_usuario/services.py`.
5. **Wrappers previos al runtime**:
   - Si `new_conversation=True`, crea `session_id` nuevo (`__newconv__...`) en RAM.
   - No toca override store, no aplica prompt/config/contextual overrides.
6. **Llamada al runtime cognitivo**:
   - `execute_turn_with_contract(...)` con `entry_surface="interfaz_usuario"`, `optimizer_wrapper_used=False`, `overrides_applied=False`.
7. **Persistencia y trazas**:
   - Misma persistencia canónica del runtime (`negotiation_canonical*`).
   - No añade `_optimizador`.
8. **Serialización respuesta**:
   - Devuelve `reply` y metadatos de continuidad (`conversation_id_*`, `previous_response_id_*`, `entry_contract`, `trace_count`).

### C) Carril legacy `/chat`
- `POST /chat` llama `run_agent(...)` (pipeline general no-negociación), no `execute_turn_with_contract` de negociación.
- No escribe `negotiation_canonical_traces`.

---

## Fase 2 — Inventario exhaustivo de diferencias reales

## Diferencias confirmadas (estructurales)
1. **Superficie de entrada y schema**: optimizador recibe metadatos de experimentación (`optimizer_session_id`, scopes), interfaz no.  
2. **Store lateral de overrides**: solo optimizador consulta `_OVERRIDE_STORE` y puede modificar config/prompts/contexto por turno/conversación/sesión.  
3. **Inyección contextual lateral**: optimizador puede reescribir `persona` en canonical state antes del runtime.  
4. **Metadata lateral en trazas**: optimizador anota `_optimizador`; interfaz no.  
5. **Semántica de clon**: solo optimizador soporta `sandbox/clone` con copia profunda + `optimizador_sandbox_meta`.  
6. **Semántica new conversation**:
   - Optimizador crea sesión nueva y además marca `optimizador_sandbox_meta.clone_strategy=new_conversation_clean_start`.
   - Interfaz crea sesión nueva sin ese metadato.
7. **Contract flags**: `optimizer_wrapper_used=True` en optimizador vs `False` en interfaz.
8. **Retorno API distinto**: optimizador devuelve `effective_overrides` + `turn_title` + objeto `turn`; interfaz devuelve payload más minimalista.

## Diferencias descartadas o debilitadas
1. **Núcleo cognitivo distinto**: no; ambos entran a `execute_turn_with_contract(...)` y de ahí a `run_negotiation_cognitive_turn(...)`.
2. **Config base distinta por defecto**: no; en baseline limpio ambos heredan snapshot idéntico de `build_negotiation_pipeline_config(...)`.
3. **Dependencia oculta de `/chat` en interfaz**: no; no hay routing interno hacia `/chat`.

---

## Fase 3 — Contexto efectivo (lo que realmente ve el pipeline)

### Hallazgo principal
- En **paridad limpia** (misma semilla de estado + sin overrides) el `config_snapshot` que entra por contrato es idéntico entre optimizador e interfaz.
- Por tanto, las diferencias de calidad remanentes no vienen del “núcleo” sino de **estado/overrides/meta del wrapper**.

### Campos comparados dinámicamente (stub forense)
- `memory_key`
- `thread_mode_default`
- `max_recent_messages`
- `max_executor_recent_turns`
- `model_memory/model_phase_classifier/model_planner/model_executor`
- `world_state_keys`
- `has_optimizer_meta`
- `recent_dialogue_count`
- continuidad OpenAI (`conversation_id_*`, `previous_response_id_*`)

El reporte JSON muestra que los campos de config base empatan en escenario limpio y se separan en cuanto se activan overrides del optimizador.

---

## Fase 4 — Trazas y evidencia

Fuente: `backend/docs/forensics_optimizer_vs_interfaz_usuario_run.json`.

Puntos observados:
1. **Scenario 1 (same seed / same message)**:
   - `same_config_snapshot: true`.
   - `overrides_applied_optimizer: false` y `overrides_applied_interfaz: false`.
2. **Scenario 2 (second turn continuity)**:
   - Ambos mantienen continuidad (`conversation_id_after` estable y `previous_response_id` evoluciona).
3. **Scenario 3 (override vs isolation)**:
   - Optimizador: `entry_contract.overrides_applied=true` y snapshot alterado por override (`max_recent_messages`, etc.).
   - Interfaz: `overrides_applied=false`, snapshot sin cambios.
4. **Scenario 4 (clone vs new conversation optimizer)**:
   - `clone_used=true` para sesión clonada.
   - `new_conversation=true` para sesión `new_conversation`.
5. **Scenario 6 (chat leakage)**:
   - `chat_added_negotiation_trace=false`: `/chat` no contamina trazas de negociación.

---

## Fase 5 — Pruebas reproducibles añadidas

1. Script diagnóstico nuevo: `backend/scripts/forensics_optimizer_vs_interfaz_usuario.py`.
2. Artifact versionado: `backend/docs/forensics_optimizer_vs_interfaz_usuario_run.json`.
3. Tests nuevos: `backend/tests/test_forensics_optimizer_vs_interfaz_usuario.py`.

---

## Fase 6 — Diferencias laterales / arrastre

1. **Override store en RAM indexado por `optimizer_session_id`**: ventaja estructural del optimizador para iterar prompts/config sin tocar código.
2. **`optimizador_sandbox_meta`**: altera flags de contrato y permite trazabilidad de clon/versionado.
3. **`_optimizador.versioning`**: habilita comparación de variantes sobre la misma base de turno (`repeat_from_turn_id`), ausente en interfaz.
4. **Contextual persona override**: puede cambiar tono/comportamiento del agente sin alterar runtime core.

---

## Fase 7 — Impacto causal en calidad percibida

1. **Overriding de config/prompts** → puede mejorar rendimiento subjetivo del optimizador porque ajusta ventana de contexto o prompts por experimento.
2. **Capacidad clone/repeat/versioning** → favorece iteración sobre estados “buenos”, lo que sesga la percepción de calidad promedio.
3. **Contextual persona override** → puede producir respuestas más “humanas” o tácticas al afinar estilo/política.
4. **Interfaz sin esos mecanismos** → comportamiento más estable, pero menos optimizable en caliente.

---

## Fase 8 — Priorización

### A) Confirmadas (evidencia fuerte)
- Diferencias de wrapper (`overrides`, `_optimizador`, clone/newconv metadata).
- Misma base de runtime en flujo limpio.
- No fuga de `/chat` al carril interfaz.

### B) Muy probables
- Parte de la mejor calidad percibida del optimizador proviene de tuning por override/config contextual.

### C) Posibles no cerradas
- Diferencias de calidad con LLM real en transiciones concretas (inicio, transición de fase, cierre) requieren corrida A/B online con clave API y capturas de `prompt_artifacts` reales.

### D) Debilitadas
- Hipótesis de “cerebro distinto” entre surfaces.

---

## Fase 9 — Propuestas de corrección (bajo riesgo)

1. **Añadir modo opcional de overrides en `interfaz_usuario` (feature flag)**
   - Archivo: `backend/interfaz_usuario/services.py`.
   - Cambio: permitir opt-in de `optimizer_session_id` para consumir `experiments_bridge.resolve_entries` en entorno controlado.
   - Ganancia: paridad experimental total sin romper default productivo.

2. **Persistir metadato mínimo de experimento en interfaz (sin exponer UI de optimizador)**
   - Archivo: `backend/negociacion/orchestration/turn_contract.py` o wrapper interfaz.
   - Cambio: guardar bloque `_surface_meta` homogéneo para auditoría comparativa.

3. **Crear prueba A/B live opcional (con API key) para prompts/payload hashes**
   - Archivo nuevo en `backend/scripts/`.
   - Cambio: comparar `prompt_artifacts.payload_hash` por nodo entre surfaces bajo mismo estado.

---

## Resumen ejecutivo
- **Qué explica hoy la diferencia**: wrappers laterales del optimizador (overrides, clone/versioning, contextual persona) y no un runtime cognitivo distinto.
- **Qué no la explica**: endpoint legacy `/chat` ni configuración base del pipeline en baseline limpio.
- **Qué queda abierto**: cuantificar cuánto mejora cada diferencia bajo modelo real (online) en transiciones críticas.
- **Siguiente mejor paso**: A/B live con payload hashes y outputs por nodo, manteniendo misma sesión semilla y activando/desactivando solo cada mecanismo lateral.
