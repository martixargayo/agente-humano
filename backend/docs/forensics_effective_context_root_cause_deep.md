# Forense raíz-causal: `optimizador` vs `interfaz_usuario` (profundización sobre `forensics_effective_context_parity_run.json`)

## 1) Resumen ejecutivo

Se reanalizó a fondo `backend/docs/forensics_effective_context_parity_run.json` y se cruzó con código + pruebas dinámicas nuevas.

Hallazgos clave:

1. **La paridad limpia sigue siendo real**: en baseline controlado, no hay divergencia de payload por nodo.
2. **El primer desalineamiento causal aparece antes de que piense `memory`**, en los inputs de construcción de `MemoryInput` (`recent_dialogue_len` y/o `memory_working_current` residuales).
3. **La cascada se confirma**: una divergencia mínima pre-memory se materializa primero en `memory`, y luego contamina phase/planner/executor.
4. **Se detectó una asimetría operativa concreta y corregible**: los IDs de `new_conversation` se generaban con resolución de segundos en ambas superficies, pudiendo colisionar si se creaban conversaciones nuevas casi simultáneamente para el mismo `user_id/session_id` base. Eso abre puerta a contaminación cruzada de estado.

## 2) Metodología

- Lectura estructural completa del JSON central (`turns`, `node_comparison`, `state_compare`, `hidden_continuity_skew`, `global_checks`).
- Correlación con runtime real de negociación (`flow_config`, `turn_contract`, servicios de superficie).
- Nuevo script forense con instrumentación en:
  - `freeze_prompt_artifacts` (payload efectivo por nodo),
  - `_call_structured` (stub determinista para eliminar variación del modelo),
  - `build_memory_input` (captura del **pre-memory** real).
- Nuevas pruebas automáticas para fijar invariantes y prevenir regresión.

## 3) Lectura forense del JSON grande (artefacto central)

`backend/docs/forensics_effective_context_parity_run.json` confirma:

- `first_payload_divergence: null` en escenario limpio.
- `global_checks.*` en true (paridad de payloads y de estado derivado durante baseline).
- En `hidden_continuity_skew`, la primera divergencia documentada aparece en `memory.recent_dialogue_short.length`.

Conclusión: el JSON grande no apunta a “cerebro distinto”, sino a **desalineamiento de contexto efectivo pre-nodo**.

## 4) Qué continuidad, dónde vive y cómo entra

Continuidad operativa relevante:

- `StateRepository.load_recent_dialogue(...)` lee de `world_state["negotiation_canonical_recent_dialogue"]`.
- `build_memory_input(...)` inyecta ese diálogo (compactado a 8) en `recent_dialogue_short`.
- `apply_memory_output_to_state(...)` refresca `memory_working` y `negotiation_state`.
- `apply_phase_classifier_output_to_state(...)` / `apply_planner_output_to_state(...)` actualizan `planner_state`.

Cadena causal:

1. Diverge `recent_dialogue` o `memory_working_current` **antes** de construir `MemoryInput`.
2. Primera divergencia visible: payload de `memory`.
3. Divergencia propagada: `memory_working` / `negotiation_state`.
4. Planner recibe estado ya sesgado y cambia plan táctico.
5. Executor verbaliza sobre plan/contexto ya desalineados.

## 5) Pruebas nuevas y resultados

Script nuevo: `backend/scripts/forensics_effective_context_root_cause.py`.
Artefacto nuevo: `backend/docs/forensics_effective_context_root_cause_run.json`.

Escenarios:

1. **clean**: paridad completa.
2. **residual_interfaz**: seed de historial oculto solo en interfaz; primera divergencia en `memory.recent_dialogue_short.length`, y `memory_input_build_first_diff=recent_dialogue_len`.
3. **residual_optimizer**: simétrico, confirma que no es propiedad intrínseca de una superficie sino del estado residual.
4. **stale_canonical_interfaz**: con `memory_working/planner_state` residuales solo en interfaz, primera divergencia en `memory.memory_working_current.current_topic`; evidencia de que `memory` cristaliza sesgo previo (no lo origina).
5. **reset_strength**: ambas superficies resetean, pero antes había riesgo de colisión de `session_id` por timestamp de segundos.

## 6) Hipótesis finas (estado)

### Confirmadas

- **H1**: `memory` no es origen primario; es primer nodo donde se hace visible un sesgo previo.
- **H2**: divergencias mínimas en continuidad residual producen cascada total en nodos posteriores.

### Muy probables

- **H3**: parte de la diferencia subjetiva proviene de calidad/limpieza del estado con que arranca cada turno (más que de diferencias en modelos/prompts base).

### Debilitadas

- “Hay otro runtime cognitivo diferente”.
- “La diferencia base depende de clone/repeat/versioning/override como causa principal” (pueden influir en casos específicos, pero no explican la base limpia).

## 7) Hallazgo adicional importante (nuevo)

Se corrigió una fuente real de contaminación potencial:

- Antes, `create_new_conversation` (interfaz) y `new_conversation_session` (optimizador) generaban IDs `__newconv__` con timestamp de **segundos**, con riesgo de colisión en llamadas casi simultáneas.
- Ahora se usa timestamp con microsegundos + sufijo aleatorio (`uuid4` corto), eliminando esa ventana de colisión.

## 8) Ranking de causas por probabilidad real

A. **Confirmada fuerte**: continuidad residual desalineada previa a `memory`.
B. **Confirmada fuerte**: posible contaminación por colisión de `new_conversation` (ya mitigada).
C. **Probable**: diferencias de uso real (resets incompletos/reutilización de sesión) explican sesgo percibido.
D. **Debilitada**: diferencias de núcleo cognitivo.

## 9) Propuestas de bajo riesgo

1. Mantener ID de conversación nueva con alta entropía (aplicado).
2. Añadir hash/contador de `recent_dialogue` y snapshot breve de `memory_working` al trace de entrada para detectar skew antes de `memory`.
3. Añadir chequeo opcional “clean-start assertion” al iniciar conversación nueva.

## 10) Siguiente mejor paso

Hacer un A/B en uso real (sin stubs) con telemetría mínima adicional de pre-memory (`recent_dialogue_len`, hash y origen de sesión) para medir frecuencia real de skew por superficie y correlacionarla con caídas de calidad percibida.
