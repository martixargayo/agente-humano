# Forense profundo: `optimizador` vs `interfaz_usuario` (residuo/contexto)

## 1) Hallazgo causal principal

La diferencia **causal** más fuerte no está en los nodos ni en el modelo: ambos carriles ejecutan el mismo runtime (`execute_turn_with_contract -> run_negotiation_cognitive_turn`).

La robustez del optimizador frente a arrastre viene de su **disciplina operativa de boundaries**:
- UI y API exponen explícitamente `sandbox/new_conversation`, `clone`, `repeat_from_turn_id`, `scope_turn_id`.
- El operador del optimizador trabaja sobre ramas/sesiones nuevas con mucha frecuencia.
- Esto corta continuidad (`session_id`, `conversation_id`, `previous_response_id`) antes de planner/executor.

`interfaz_usuario`, en cambio, recicla más la sesión “principal”; su auto-reset existía pero era más estrecho. El fix aplicado amplía ese boundary protector sin rediseño.

---

## 2) Mapa diferencial verificado

### A. Igualdades estructurales (descartan “otro cerebro”)
1. Ambas superficies llegan a `execute_turn_with_contract(...)`.
2. Ambas usan `build_negotiation_pipeline_config()` por defecto.
3. Ambas ejecutan el mismo pipeline cognitivo: memoria/fase/planner/executor, mismas políticas de threading y mismas estructuras de trace.

### B. Diferencias reales relevantes
1. **Superficie optimizador** añade instrumentos de branching: `clone`, `new_conversation`, `repeat_from_turn_id`, `scope_turn_id`.
2. **Override store** sólo en optimizador: puede variar prompt/config/contexto por sesión experimental.
3. **Metadata de sandbox** (`optimizador_sandbox_meta`) marca estrategia (`full_session_with_preferred_conversation` vs `new_conversation_clean_start`) y termina reflejándose en contrato de entrada (`clone_used`, `new_conversation`).
4. `interfaz_usuario` no tenía instrumentación equivalente de ramas; dependía de `new_conversation` manual y una heurística de auto-reset más restrictiva.

---

## 3) Primer punto exacto de divergencia

El primer punto útil de divergencia aparece **antes del planner**: en el wrapper de entrada (`services.run_turn` / `services.run_sandbox_turn`), al decidir si el turno entra en sesión continua o en sesión limpia.

- Nodo: *entry wrapper* (pre-runtime).
- Campo: `session_id` efectivo + continuidad OpenAI (`previous_response_id`/`conversation_id`) heredada del canonical state.
- Impacto: esa continuidad alimenta `refresh_request_context(...)` y la selección de contexto para planner/executor.

---

## 4) Evidencia reproducible (harness)

Artefacto: `backend/docs/forensics_optimizer_vs_interfaz_usuario_run.json`.

Escenarios verificados:
1. **Baseline limpio A/A**: mismo estado semilla, mismo mensaje, mismo snapshot de config (`same_config_snapshot=true`).
2. **Continuidad simétrica**: ambas superficies mantienen continuidad similar en segundo turno.
3. **Override vs aislamiento**: optimizador altera snapshot efectivo cuando hay overrides; interfaz no.
4. **Clone vs new conversation (optimizador)**: flags de contrato reflejan el boundary (`clone_used` / `new_conversation`).
5. **`/chat` leak check**: `/chat` no añade trazas de negociación.
6. **Boundary auto-reset interfaz (nuevo)**: con estado “sticky” + intención explícita de reinicio (“empecemos de cero”), interfaz corta a nueva sesión y el contrato ya marca `new_conversation=true`.

---

## 5) Fix mínimo aplicado

### Cambio runtime (bajo riesgo)
En `backend/interfaz_usuario/services.py`:
1. Se amplió `_should_auto_reset_for_fresh_opener(...)` para detectar riesgo de arrastre no sólo por fase terminal, sino también por señales de continuidad sticky:
   - `planner_state.current_turn_goal` no vacío,
   - `openai_thread.previous_response_id` presente,
   - o ventana reciente suficientemente larga.
2. Se añadieron intents explícitos de boundary (“empecemos de cero”, “nuevo caso”, “nueva negociación”, etc.).
3. Cuando el auto-reset dispara, ahora `TurnEntryContract.new_conversation` se marca como `True` (antes quedaba `False` en auto-reset implícito).

### Por qué ataca la causa
Replica en interfaz el mecanismo protector operativo del optimizador: **forzar boundary temprano ante señales de arrastre**, sin tocar prompts/modelos/nodos.

### Riesgo
Bajo: cambio localizado en wrapper de `interfaz_usuario`, reversible, sin romper contratos de API ni modificar pipeline cognitivo.

---

## 6) Validación

- Tests de API/forense actualizados y en verde.
- Script forense regenerado con escenario específico de boundary sticky.

---

## 7) Estado del caso

**Parcialmente cerrado con evidencia causal fuerte a nivel de lifecycle/boundary**:
- Confirmado: la ventaja del optimizador viene en gran parte de cómo se segmentan episodios y se evita reuse continuo.
- Replicado: interfaz ahora hereda esa protección con un fix mínimo.
- Pendiente (si se quiere cierre absoluto): corrida live con modelo real y scoring cuantitativo de “humanidad” por escenarios largos, pero ya no es requisito para validar la causa de lifecycle/contexto.
