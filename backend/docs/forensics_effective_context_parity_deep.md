# Forense profundo de contexto efectivo: `optimizador` vs `interfaz_usuario`

## 1) Resumen ejecutivo
- Se ejecutó una comparación A/B **por nodo** (memory, phase_classifier, planner, executor) con el mismo runtime, misma semilla, mismo mensaje y sin overrides manuales.
- Resultado central: en condiciones controladas limpias, los payloads de nodo son isomorfos entre superficies (salvo campos efímeros como `turn_id/timestamp`, normalizados en la comparación).
- El **primer punto causal de divergencia real** apareció al introducir continuidad residual solo en una superficie: `memory.recent_dialogue_short.length` diverge y desde ahí arrastra diferencias a phase/planner/executor.
- Conclusión fuerte: la diferencia de calidad restante no apunta al “cerebro”, sino a **continuidad efectiva / estado residual** que cambia el contexto que ve el runtime.

---

## 2) Hipótesis descartadas definitivamente
1. Núcleo cognitivo distinto entre superficies.
2. Diferencia por clone/repeat/versioning como causa base (no usados en experimento limpio).
3. Overrides manuales como causa principal en baseline (desactivados).

---

## 3) Hipótesis abiertas
1. En producción real (con modelo online) una diferencia pequeña de `recent_dialogue_short` puede amplificarse en `memory_working` y en decisiones de planner.
2. La gestión operativa de sesión (reutilización de IDs, historial residual en RAM) puede sesgar comparativas subjetivas si no se limpia explícitamente.

---

## 4) Metodología
- Lectura estática de builders y updates de estado en `flow_config.py`.
- Harness dinámico que intercepta `freeze_prompt_artifacts` + `_call_structured` para capturar payloads efectivos por nodo y evitar ruido de red/modelo.
- Escenarios:
  - **A/B limpio** (4 turnos equivalentes, sin overrides, sin clone/repeat).
  - **Skew de continuidad oculta** (misma entrada visible, pero con `recent_dialogue` residual en un solo carril).

---

## 5) Mapa E2E de ambos carriles
- Ambos carriles acaban en `execute_turn_with_contract(...)` y de ahí en `run_negotiation_cognitive_turn(...)`.
- La construcción de `MemoryInput`, `PhaseClassifierInput`, `PlannerInput`, `ExecutorInput` se hace en las mismas funciones compartidas.
- Las mutaciones de `memory_working`, `planner_state`, `negotiation_state` también son compartidas (`apply_*_to_state`).

---

## 6) Análisis detallado por bloque sospechoso

### 6.1 `recent_dialogue_short`
- Fuente compartida: `repo.load_recent_dialogue(...)` + `_compact_recent(...)`.
- En baseline limpio, ambos carriles producen el mismo recorte/orden normalizado.
- En skew residual, la primera divergencia ocurre en `memory.recent_dialogue_short.length`.

### 6.2 `memory_working`
- Se actualiza solo en `apply_memory_output_to_state(...)` desde `MemoryOutput.working_memory_new`.
- Si `MemoryInput.recent_dialogue_short` diverge, la memoria resultante puede divergir desde ese turno.

### 6.3 `planner_state`
- Se toca por `apply_phase_classifier_output_to_state(...)` y `apply_planner_output_to_state(...)`.
- En baseline limpio queda isomorfo.
- En skew potencialmente diverge por efecto dominó de `memory`/`phase` (en evidencia: el primer corte está antes, en memory input).

### 6.4 `negotiation_state`
- Se sustituye por snapshot de `memory` cada turno (`apply_memory_output_to_state`).
- Por diseño, cualquier diferencia en memoria contextual puede cambiar:
  - `last_offer_self/other`
  - `active_axes`
  - `blockers`
  - `next_open_loop`

### 6.5 Continuidad efectiva
- Sin `conversation_id` operativo, la continuidad útil recae en canonical state + recent dialogue + estados derivados.
- Esto refuerza que estado residual/hidratación pesan más que metadata superficial de wrapper.

### 6.6 Context tuning residual
- En baseline sin overrides no se observó tuning contextual activo que altere payloads entre superficies.
- El tuning residual más crítico observado fue continuidad residual (estado previo), no patching manual.

---

## 7) Evidencia experimental
- Artefacto JSON: `backend/docs/forensics_effective_context_parity_run.json`.
- Script reproducible: `backend/scripts/forensics_effective_context_parity.py`.
- En `global_checks` de baseline: paridad total de payloads y estados comparados.
- En `hidden_continuity_skew`: primera divergencia en `memory.recent_dialogue_short.length`.

---

## 8) Primer punto exacto de divergencia encontrado
- `node = memory`
- `path = recent_dialogue_short.length`
- Escenario: mismo mensaje visible, pero una superficie tiene continuidad residual no compartida.

---

## 9) Impacto causal probable en calidad
1. Menor/mayor ventana real de diálogo cambia la lectura de contexto táctico.
2. Esto altera `memory_working` y `negotiation_state` del turno.
3. El planner recibe estado distinto y cambia objetivo/decisión.
4. El executor termina realizando una táctica distinta, percibida como “mejor” o “peor”.

---

## 10) Ranking de causas por probabilidad
### A. Confirmadas
- Divergencia por continuidad residual (`recent_dialogue_short`) como primer punto causal.
- Paridad de payloads en baseline limpio sin overrides.

### B. Muy probables
- Diferencias de higiene de sesión (limpieza/reutilización) explican gran parte de la brecha subjetiva.

### C. Posibles (pendientes live)
- Amplificación en modelo online por prompt sensitivity aunque el delta inicial sea pequeño.

### D. Debilitadas
- “Runtime distinto”, “/chat leak como causa estructural principal”, “overrides manuales siempre activos”.

---

## 11) Propuestas concretas de corrección (bajo riesgo)
1. Añadir endpoint/tooling de **reset fuerte de continuidad** para paridad experimental en ambas superficies.
2. Añadir trazado explícito en respuesta de turno con `recent_dialogue_count` y hash de payload de memory/planner para auditoría.
3. Añadir test de regresión de paridad de payload por nodo (A/B limpio) + test de divergencia controlada por continuidad residual.
4. UI: mostrar warning cuando se usa una sesión con historial previo no vacío para evitar comparativas sesgadas.
