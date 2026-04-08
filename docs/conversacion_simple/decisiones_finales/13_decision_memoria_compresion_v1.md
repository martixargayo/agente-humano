# 13 · Decisión cerrada V1 — memoria y compresión en `conversacion_simple`

## Estado

- **Estado:** Cerrada para V1
- **Alcance:** runtime online 1-LLM + política de memoria operativa

---

## 1) Hechos observados del sistema actual (base de decisión)

1. `negociacion` ya recorta `recent_dialogue` por ventana (`max_recent_messages`) en runtime.
2. `memory_episodic` se extiende por turno y no tiene trimming estructural fuerte en la ruta principal observada.
3. la “memoria” rica actual depende de llamada dedicada `memory`.

### Rutas

- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/nodes/memory_node.py`
- `backend/negociacion/state/canonical_state.py`

---

## 2) Comparativa corta de opciones

## A) Inline en la única llamada

- Pro: simplicidad de arquitectura aparente (todo junto).
- Contra: prompt sobredimensionado, mayor riesgo de latencia y fragilidad en JSON.

## B) Post-turn síncrona

- Pro: mejor calidad de resumen que determinista puro.
- Contra: rompe objetivo operativo de 1 LLM en camino crítico por latencia.

## C) Diferida (async)

- Pro: preserva latencia de turno y objetivo 1-LLM online.
- Contra: requiere mecanismo de ejecución diferida y control de retries.

## D) 100% determinista

- Pro: costo e infraestructura mínima.
- Contra: peor fidelidad semántica a medio plazo.

## E) Híbrida

- Pro: equilibrio realista entre latencia, robustez y fidelidad.
- Contra: complejidad moderada (dos modos de compresión).

---

## 3) Decisión cerrada para V1

### En V1 se hará X

1. **`recent_dialogue`** se mantendrá con ventana fija de **12 mensajes** (configurable).
2. Se aplicará **trimming determinista inmediato** en cada turno para `recent_dialogue`.
3. Existirá **`memory_compacted_summary`** en estado canónico de `conversacion_simple`.
4. La compresión histórica será **diferida (async)** como modo principal.
5. La única llamada online del turno será el nodo **`brain`**.

### En V1 no se hará Y

1. No se ejecutará una segunda llamada LLM síncrona post-turn para compresión.
2. No se usará compresión inline obligatoria dentro de la llamada `brain` para todo histórico.
3. No se intentará un sistema multi-nodo online equivalente al de `negociacion`.

### Se acepta Z trade-off

- Se acepta que la compresión pueda no ocurrir inmediatamente tras cada turno (eventual consistency de memoria compactada).

### Fallback W

- Si compresión diferida falla/no corre: **fallback determinista** que sintetiza histórico remoto en formato conservador (sin bloquear turno).

---

## 4) Política operativa V1 (detallada)

## 4.1 `recent_dialogue`

- Guardar siempre últimos 12 mensajes en alta fidelidad.
- Trimming por cola (drop oldest) al superar umbral.

## 4.2 Memoria episódica

- `brain` emite `episodic_append` por turno.
- Retención en alta resolución con umbral (`episodic_high_res_limit`, p.ej. 40 eventos).
- Al superar umbral, candidatos antiguos pasan a cola de compresión diferida.

## 4.3 `memory_compacted_summary`

- Campo textual/estructurado resumido de histórico remoto.
- Se actualiza por job diferido o por fallback determinista.

## 4.4 Trigger de compresión

- Trigger principal: superar límite de episodic alta resolución.
- Trigger secundario: tamaño de payload histórico en chars/tokens.

## 4.5 Fallos

- Si job diferido falla: registrar evento + reason code + retry budget.
- Si agota retries: aplicar fallback determinista y marcar degradación.

---

## 5) Justificación de la decisión

## Simplicidad real

- Mantiene 1-LLM online sin introducir llamada síncrona extra.

## Robustez

- turno no depende de infraestructura de compresión para responder.

## Coste y latencia

- coste principal por turno permanece bajo/controlado.
- compresión se mueve fuera del camino crítico.

## Complejidad operativa

- añade complejidad moderada (cola/job), pero acotada y observable.

## Infraestructura adicional

- sí, se requiere mecanismo diferido básico (scheduler/worker ligero).
- en ausencia, fallback determinista evita bloqueo funcional.

## Fidelidad del contexto a medio plazo

- mejor que 100% determinista puro.
- más estable que compresión ocasional manual.

---

## 6) Impacto futuro

## Qué deja preparado

1. Evolución a compresión inteligente por prioridad semántica.
2. Ajuste dinámico de ventanas por perfil de conversación.
3. Métricas de calidad de resumen y deriva contextual.

## Deuda que introduce

1. necesidad de gobernar job diferido y retries.
2. dos rutas de resumen (diferida + fallback) a validar consistentemente.

## Métricas a vigilar

1. ratio de compresiones ejecutadas vs omitidas,
2. ratio de fallback activado,
3. crecimiento de memoria episódica,
4. latencia p95 de turno,
5. degradación percibida en conversaciones largas.

---

## 7) Contrato observable (trace/log)

En V1 se registrará explícitamente:

1. `memory_recent_dialogue_count_before` / `after`.
2. `memory_recent_dialogue_trimmed_count`.
3. `memory_compression_mode` = `none | deferred_llm | deterministic_fallback`.
4. `memory_compression_status` = `scheduled | executed | skipped | failed | fallback_applied`.
5. `memory_compression_reason` (si skipped/failed).
6. `memory_compacted_summary_chars_before` / `after`.
7. `memory_episodic_count_before` / `after`.
8. `memory_growth_anomaly_flag` (bool) si supera umbral duro.

---

## 8) Cierre formal

La política V1 de memoria/compresión queda cerrada como:

- **online:** 1 LLM (`brain`) + trimming determinista de `recent_dialogue`;
- **off-path:** compresión diferida;
- **fallback:** determinista no bloqueante.

No se reabre esta decisión en fase de implementación salvo incidencia crítica validada.
