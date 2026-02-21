# LiveTrace2 — Plan de implementación (versión separada)

## 1) Objetivo de producto
Construir **LiveTrace2** como un sistema independiente de LiveTrace1, con foco en **transparencia total del flujo real de ejecución** por turno.

Resultado esperado en cada turno:
- Ver todas las LLM y gates ejecutados en orden.
- Ver el **prompt real de entrada** enviado a cada LLM (post-render, no plantilla de código).
- Ver la **salida real** de cada LLM.
- Ver en cada gate:
  - datos de entrada usados,
  - resultado de salida,
  - evidencia/criterio de por qué salió ese resultado.
- Ver latencia por fase/nodo y total de turno.
- Sin resúmenes automáticos: solo trazas completas y navegables.

> Principio clave: LiveTrace2 no extiende LiveTrace1; se entrega como **pipeline de tracing paralelo** con su propio contrato de datos, backend y UI.

## 2) Principios no funcionales
- **Fidelidad**: capturar payload exacto enviado/recibido.
- **Legibilidad**: UI por bloques “Entrada → Salida” para cada nodo.
- **Orden temporal**: secuencia estricta con timestamps y duración.
- **Aislamiento**: no romper LiveTrace1 ni depender de su schema.
- **Auditoría**: trazas reproducibles por `session_id + turn + node`.

## 3) Alcance funcional de LiveTrace2
### Incluye
1. Nuevo schema de eventos (`livetrace2_event`).
2. Instrumentación en runtime para LLM calls y gates.
3. Persistencia de eventos por turno.
4. API de consulta (timeline + detalle por nodo).
5. UI dedicada con grafo/secuencia y paneles de detalle.
6. Métricas de latencia por nodo/fase/turno.

### Excluye
- Reescritura de LiveTrace1.
- Resúmenes de razonamiento.
- Compresión o agregación que oculte datos de entrada/salida.

## 4) Modelo conceptual
### Entidades
- **TraceSession**: sesión completa.
- **TraceTurn**: un turno de conversación.
- **TraceNodeExecution**: ejecución atómica de un nodo (LLM o gate).
- **TraceEdge**: relación entre nodos (flujo de datos/control).

### Tipos de nodo
- `llm_call`
- `gate`
- `tool_call` (opcional futuro, dejar preparado)

## 5) Contrato de datos (v2)
Definir un nuevo schema JSON, por ejemplo `docs/livetrace2_event.schema.json`.

Campos mínimos por `TraceNodeExecution`:
- Identidad:
  - `trace_id`, `turn_id`, `node_id`, `node_name`, `node_type`
- Orden y tiempo:
  - `started_at`, `ended_at`, `latency_ms`, `sequence_index`
- Entrada real:
  - `input_payload_raw` (JSON o texto)
  - `input_prompt_rendered` (solo para LLM)
- Salida real:
  - `output_payload_raw`
  - `output_text_rendered` (si aplica)
- Explicabilidad gate:
  - `gate_rule_id` / `gate_version`
  - `gate_evidence` (datos usados)
  - `gate_decision`
  - `gate_decision_reason`
- Estado:
  - `status` (`ok|error|timeout|skipped`)
  - `error` (si aplica)
- Relación de flujo:
  - `parent_node_id`, `prev_node_id`, `next_node_ids`

## 6) Diseño de instrumentación backend
## 6.1. Nueva capa: `livetrace2_runtime`
Crear módulo dedicado (separado de `live_trace.py`) con:
- `start_turn_trace(turn_ctx)`
- `start_node(node_meta, input_payload)`
- `record_llm_prompt(rendered_prompt, request_payload)`
- `record_llm_output(response_payload)`
- `record_gate_decision(evidence, decision, reason)`
- `end_node(status, error=None)`
- `end_turn_trace()`

## 6.2. Puntos de hook obligatorios
- Antes de invocar cada LLM: capturar prompt final renderizado.
- Después de respuesta LLM: capturar output completo.
- En gates: capturar entradas concretas consultadas + decisión + razón.
- En errores/timeouts: cerrar nodo con estado y latencia.

## 6.3. Regla de oro de captura
Guardar lo que realmente circula por runtime:
- Si se transforma prompt antes de enviar, guardar versión transformada final.
- Si se parsea salida, guardar también output crudo original.

## 7) Persistencia y consulta
### 7.1 Persistencia
- Tabla/colección nueva `livetrace2_events` (o equivalente).
- Índices sugeridos:
  - `(session_id, turn_id, sequence_index)`
  - `(trace_id, node_id)`
  - `(created_at)`

### 7.2 API
Endpoints sugeridos:
- `GET /api/livetrace2/sessions/{session_id}/turns`
- `GET /api/livetrace2/turns/{turn_id}/timeline`
- `GET /api/livetrace2/nodes/{node_id}`

Respuesta de timeline:
- lista ordenada de nodos,
- edges,
- latencia total y por tipo,
- métricas de completitud (nodos con input/output capturados).

## 8) UX/UI (atractiva y entendible)
## 8.1 Layout principal
- **Columna izquierda**: grafo/secuencia de nodos (LLM y gates).
- **Panel derecho**: detalle del nodo seleccionado.

## 8.2 Tarjeta de nodo (vista detalle)
Estructura fija y visual:
1. Header: nombre, tipo, estado, latencia.
2. Caja A “Entrada real” (monoespaciado, copy button).
3. Caja B “Salida real” (monoespaciado, copy button).
4. Si es gate:
   - “Información usada”
   - “Resultado”
   - “¿Por qué este resultado?”
5. Footer: timestamps e IDs técnicos.

## 8.3 Visualización de latencias
- Badge por nodo (`XX ms`).
- Barra comparativa por fase.
- KPI arriba: total turno, p95 nodo, nodo más lento.

## 8.4 Legibilidad anti-“acumulación de código”
- No mostrar estructuras internas irrelevantes por defecto.
- Mostrar JSON/raw en bloques claros, con colapsado por secciones.
- Navegación por pasos (anterior/siguiente nodo).

## 9) Seguridad y privacidad
- Redactado opcional configurable por campo sensible (PII/secrets).
- Modo “full internal” solo para entornos autorizados.
- Trazas con política de retención (ej. 7/30 días configurable).

## 10) Plan de implementación por fases
## Fase 0 — Alineación de contrato (2–3 días)
- Definir schema v2 final.
- Acordar lista de nodos/gates a instrumentar inicialmente.
- Definir política de redacción y retención.

## Fase 1 — Instrumentación mínima funcional (4–6 días)
- Implementar `livetrace2_runtime`.
- Hook en 2–3 LLM críticas + gates principales.
- Persistir eventos completos por turno.

Criterio de aceptación:
- Para un turno real, se ven prompts de entrada/salida reales y latencias por nodo.

## Fase 2 — API + timeline (3–5 días)
- Endpoints de sesiones, turnos y nodos.
- Orden estable por `sequence_index`.
- Edge mapping básico entre nodos.

Criterio de aceptación:
- Un cliente puede reconstruir flujo completo de turno sin lógica adicional.

## Fase 3 — UI LiveTrace2 (5–8 días)
- Vista timeline/grafo + panel detalle.
- Cajas “Entrada” y “Salida” lado a lado.
- Sección de gates con “info usada / resultado / razón”.
- Métricas de latencia visibles.

Criterio de aceptación:
- Usuario no técnico puede seguir un turno extremo a extremo.

## Fase 4 — Hardening y adopción (3–5 días)
- Cobertura de todos los nodos críticos.
- Manejo de errores/timeouts/reintentos.
- Performance tuning y controles de volumen.

Criterio de aceptación:
- Trazabilidad completa en >95% de turnos sin degradación sensible.

## 11) Estrategia de validación
### Pruebas backend
- Unit tests de captura de prompt real/output real.
- Tests de orden temporal y latencias.
- Tests de gates (evidence + reason obligatorios).
- Tests de errores con cierre correcto de nodo.

### Pruebas de contrato
- Validación estricta contra schema v2.
- Pruebas de compatibilidad de API con dataset real.

### Pruebas UI
- Snapshot/visual tests de tarjeta de nodo.
- E2E: abrir turno, navegar nodos, verificar contenido entrada/salida.

## 12) Riesgos y mitigaciones
- **Volumen de datos alto** → compresión en almacenamiento, paginación en API/UI.
- **Sensibilidad de datos** → redacción por política + control de acceso fuerte.
- **Instrumentación incompleta** → checklist por nodo y dashboard de cobertura.
- **Sobrecoste de latencia** → captura asíncrona donde sea posible.

## 13) Entregables
1. Documento de arquitectura LiveTrace2.
2. Schema `livetrace2_event` versionado.
3. Runtime e instrumentación backend.
4. Endpoints API documentados.
5. UI LiveTrace2 funcional.
6. Suite de tests + métricas de cobertura de trazas.

## 14) Definición de éxito
LiveTrace2 se considera logrado cuando, en un turno cualquiera:
- Se observa el flujo completo de LLM/gates en secuencia.
- Cada nodo muestra entrada real y salida real.
- Cada gate muestra datos usados, resultado y razón.
- Cada fase muestra latencia.
- La lectura es clara, visual y accionable sin depender de resúmenes.
