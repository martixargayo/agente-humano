# Plan de transición para eliminar código transicional sin romper el flujo actual

## Alcance
Este plan cubre únicamente zonas que **hoy aportan poco o nada al runtime principal**, pero cuyo borrado directo puede romper tests, harnesses o capacidades potenciales.

Flujo que no se debe romper: `world_updater -> belief_updater -> policy_progress -> phase_policy_planner -> progress_updater -> executor`.

---

## 1) `backend/negotiation/belief_state_updater.py`

### Estado real
- **No usado por el runtime principal** del nodo belief (el nodo usa `extract_belief_state_llm_v1` directamente).
- **Sí usado de forma indirecta** por contrato de `state/deps.py` y por tests/harnesses que mockean `deps.update_belief_state`.

### Riesgo si se borra hoy
- Se rompen tests/harnesses que esperan ese contrato.
- Puede romper utilidades de testing que dependen de `fake_update_belief_state`.

### Partes internas y utilidad
- `update_belief_state(...)`: útil solo como capa de compatibilidad.
- `merge_belief_buckets_update_not_rewrite(...)`: útil para tests de merge.
- `_BeliefDeps`: wrapper legacy, prescindible tras migración.

### Plan de transición (paso a paso)
1. **Introducir adaptador estable** en `state/deps.py` (ej. `update_belief_state_compat`) que no dependa del archivo legacy.
2. Migrar tests/harnesses para usar:
   - o el nodo real (`belief_node`),
   - o el nuevo adaptador.
3. Mantener deprecado `belief_state_updater.py` una release (mensaje de deprecación en tests internos).
4. Eliminar archivo legacy cuando 0 tests lo importen.

### Criterio de salida
- `rg "belief_state_updater|fake_update_belief_state" backend/tests backend/scripts` sin referencias funcionales al módulo legacy.

---

## 2) `backend/negotiation/gating/gate_belief.py`

### Estado real
- No entra en el flujo principal actual del `belief_updater_node`.
- Sí aparece en tests unitarios de gating.

### Riesgo si se borra hoy
- Rotura de tests de gating y pérdida de una pieza que podría reintroducirse si vuelve el gating de belief.

### Partes internas y utilidad
- `gate_belief(...)`: lógica completa pero desacoplada del runtime actual.

### Plan de transición
**Ruta recomendada (si no se va a reintroducir):**
1. Marcar tests de `gate_belief` como legacy o moverlos a suite `legacy_gating`.
2. Replicar mínimas aserciones importantes en tests del flujo real (`belief_node`) para no perder cobertura útil.
3. Eliminar `gate_belief.py` y limpiar export en `gate_utils.py`.

**Ruta alternativa (si sí se va a usar):**
1. Integrar `gate_belief` en `belief_updater_node` con feature flag.
2. Validar impactos en trace/runtime.
3. Quitar flag cuando esté estable.

### Criterio de salida
- Decisión explícita A/B tomada y documentada.

---

## 3) `backend/negotiation/elementos/belief/belief_contracts.py`
## 4) `backend/negotiation/elementos/belief/belief_updater_v2_prompts.py`

### Estado real
- No forman parte del runtime v3 principal.
- Se usan como soporte de tests/legado conceptual.

### Riesgo si se borra hoy
- Rotura de tests que importen constantes/modelos de estos módulos.

### Plan de transición
1. Crear `backend/tests/legacy_fixtures/belief_contracts_legacy.py` con las constantes mínimas que aún necesiten tests.
2. Migrar imports de tests a esas fixtures.
3. Eliminar `belief_updater_v2_prompts.py` (si no hay runtime que lo consuma).
4. Eliminar `belief_contracts.py` cuando no quede ningún import productivo.

### Criterio de salida
- `rg "elementos\.belief\.belief_contracts|belief_updater_v2_prompts" backend/tests backend` solo devuelve referencias en docs de migración (o cero).

---

## 5) `backend/negotiation/policy_docs/*.md`

### Estado real
- Son input documental para RAG por configuración (`rag_dir`), pero el uso efectivo está condicionado a la ruta de tácticas.

### Riesgo si se borra hoy
- Si se activa/usa RAG táctico, degradas calidad del sistema (aunque no falle duro).

### Plan de transición
1. Decidir estrategia oficial:
   - **Integrar** RAG táctico explícitamente en planner/executor, o
   - **Descontinuar** RAG táctico y cambiar default `rag_dir` a vacío/controlado.
2. Si se descontinúa:
   - Cambiar config para no apuntar por defecto a `policy_docs`.
   - Añadir test que garantice comportamiento sin esos archivos.
3. Solo después eliminar `policy_docs/*.md`.

### Criterio de salida
- Config por defecto no depende de esos archivos + tests verdes en modo sin RAG.

---

## 6) `backend/negotiation/phase_docs/*.md`

### Estado real
- No conectados al runtime de nodos actual.
- Valor principalmente documental.

### Riesgo si se borra hoy
- Pérdida de contexto funcional para equipo/producto.

### Plan de transición
1. Moverlos a `docs/negotiation/phase_legacy/`.
2. Actualizar enlaces internos/doc principal.
3. Borrar de `backend/negotiation/phase_docs` después de confirmar que ningún script interno los consume.

### Criterio de salida
- `rg "phase_docs|fase_[1-5]_" backend scripts docs` sin dependencias ejecutables.

---

## 7) `backend/negotiation/config/README.md`

### Estado real
- No runtime; solo guía operativa.

### Riesgo si se borra hoy
- Pérdida de documentación de configuración de modelos.

### Plan de transición
1. Migrar contenido útil a `docs/operacion/negotiation_model_config.md`.
2. Mantener un stub corto en ubicación original por 1 ciclo.
3. Eliminar stub cuando enlaces/documentación estén actualizados.

---

## Matriz final de ejecución

| Zona | Puede borrarse ya | Requiere transición | Bloqueo principal |
|---|---:|---:|---|
| `belief_state_updater.py` | No | Sí | tests/harness + contrato deps |
| `gating/gate_belief.py` | No | Sí | tests/decisión de producto |
| `elementos/belief/*` (legacy) | No | Sí | tests legado |
| `policy_docs/*.md` | No | Sí | estrategia RAG |
| `phase_docs/*.md` | No | Sí | conservación de conocimiento |
| `config/README.md` | No | Sí | documentación operativa |

---

## Checklist operativo (orden recomendado)
1. Migrar tests/harness de `belief_state_updater`.
2. Decidir destino de `gate_belief` (integrar o eliminar).
3. Extraer/migrar fixtures legacy de `elementos/belief/*`.
4. Definir estrategia oficial de RAG y actuar sobre `policy_docs`.
5. Reubicar documentación (`phase_docs`, `config/README`).
6. Ejecutar barrido final de referencias y borrar remanentes.
