# Diagnóstico técnico — degradación en última milla de negociación

## 1) Resumen ejecutivo

- La degradación reportada **sí puede originarse en el executor** por contrato permisivo: el sistema acepta `planner.status="plan"` con `executor.status="clarify"` como alineado en evaluación stub y en señales de guardrail de contrato. No hay enforcement para corregirlo automáticamente.
- El schema de `ExecutorOutput` valida forma JSON pero no fidelidad al plan (no valida `must_include`, `must_avoid`, `max_questions`, ni fidelidad de rol).
- El guardrail de salida detecta algunas clases de riesgo, pero el incumplimiento planner→executor se queda en modo observado/no aplicado para este caso concreto.
- Históricamente, `/optimizador` ya usaba `run_negotiation_cognitive_turn` desde su introducción (no aparece bypass a otro generador final dentro del periodo auditado). La unificación reciente con `/interfaz_usuario` comparte explícitamente el mismo runtime y endpoint útil, por lo que **sí propaga el mismo comportamiento del último tramo** a ambos entrypoints.
- El commit `a1939b2` no toca wiring del executor ni rutas de chat útiles (está centrado en phase/planner/finish rules), por lo que no emerge como punto causal directo de este síntoma.

## 2) Flujo actual exacto (mapa)

### 2.1 `/optimizador` (tab Chat)
1. Frontend `optimizador/app.js` delega envío/refresh/poll en runtime compartido `createOptimizadorChatRuntime`.
2. Runtime compartido (`shared/chat_runtime.js`) llama `POST /api/optimizador/sandbox/turn` para cada turno.
3. Router FastAPI `/api/optimizador/sandbox/turn` delega a `services.run_sandbox_turn`.
4. `run_sandbox_turn` llama `run_negotiation_cognitive_turn(state, message, config)`.
5. Orquestación ejecuta nodos memory + phase (paralelo), luego planner, luego executor; salida final = `executor_output.spoken_text` (posguardrail).

### 2.2 `/interfaz_usuario`
1. `interfaz_usuario/app.js` usa el mismo runtime compartido `createOptimizadorChatRuntime`.
2. Por diseño, usa el mismo endpoint útil (`/api/optimizador/sandbox/turn`) y mismo recorrido backend.

### 2.3 `/avatar` (aplicación original)
1. `avatar_app/app.js` usa `fetchAgentReply` y elige endpoint por modo:
   - `/chat` (modo chat general)
   - `/negociar` (modo negociación)
2. `/negociar` en `api/app.py` llama `run_negotiation_agent`, que resuelve al mismo core cognitivo (`run_negotiation_cognitive_turn` vía `pipeline.py`).

### 2.4 Responsabilidades explícitas
- **Estrategia**: planner (`PlannerOutput`).
- **Redacción final**: executor (`ExecutorOutput.spoken_text`).
- **Validación estructural**: `_call_structured` + `pydantic model_validate` (forma JSON/schema).
- **Guardrails post-executor**: `run_output_guardrails` (con semántica observe-only para reglas no críticas).
- **Respuesta al frontend**: `reply = executor_output.spoken_text` tras guardrails.

## 3) Comparación histórica (avatar / optimizador / interfaz_usuario)

### 3.1 Hechos confirmados
- `/optimizador` nace ya cableado a `run_negotiation_cognitive_turn` en `services.py` (sin evidencia de bypass en el periodo auditado).
- La unificación reciente (`8ca5e28`) introduce `/interfaz_usuario` y extrae runtime compartido que centraliza endpoints de chat en `/api/optimizador/*`.
- Tests de paridad confirman que ambos (`/optimizador`, `/interfaz_usuario`) cargan el mismo runtime y el mismo endpoint útil de turno.

### 3.2 Sobre `a1939b2`
- `a1939b2` (merge PR #317) modifica phase/planner/finish button tests y tipos, **no** wiring del executor ni rutas de chat final.
- Con evidencia de diff, no parece el cambio que introduce este síntoma concreto en última milla.

### 3.3 Lectura causal histórica
- Si antes se percibía “mejor” un camino, en el estado auditado **no hay diferencia sustantiva de backend final** entre `/optimizador` y `/interfaz_usuario`: comparten mismo executor y mismas reglas de postproceso.
- Por tanto, una unificación de front/ruta útil sí puede haber **propagado visibilidad** del mismo defecto a más superficies.

## 4) Auditoría técnica del executor

### 4.1 ¿Puede devolver `clarify` cuando planner está en `plan`?
Sí, por tres capas:
1. Schema `ExecutorOutput.status` permite literal `clarify` sin condicionar por planner.
2. Señales de contrato (`_planner_contract_signals`) no marcan violación para `plan -> clarify` (solo castiga `plan -> refuse`).
3. Evaluación stub considera `plan + clarify` como aligned.

### 4.2 ¿Qué no está validado hoy?
- `must_include` del planner contra `spoken_text`.
- `must_avoid` del planner contra `spoken_text`.
- `limits.max_questions=0` (no hay validador contractual de preguntas).
- Fidelidad de rol conversacional (evitar lenguaje operador/copiloto/meta).
- Prohibición de “pedir permiso para ejecutar el plan”.

### 4.3 Guardrails de salida
- El guardrail computa `planner_contract_signals`, pero con lógica actual este caso queda sin violación contractual explícita.
- Además, aunque detecte reglas observadas, el diseño mantiene modo observado/no aplicado para muchas clases no críticas.

### 4.4 Fallbacks
- `_executor_fallback` para planner `plan` devuelve `deliver` genérico (“Entiendo…”), pero no materializa `must_include`; es seguro como forma, no fiel como contenido táctico.

## 5) Reproducción controlada (caso crítico)

Se añadieron tests diagnósticos que replican exactamente el patrón:
- planner `plan/counter` con `must_include` de contraoferta 6500 y `max_questions=0`.
- executor `clarify` con pregunta meta (“¿Quieres que mantenga…?”).

Resultados que confirman el gap actual:
1. El contrato planner→executor no reporta violación para `plan -> clarify`.
2. La evaluación stub marca ese par como alineado.
3. El output guardrail no fuerza corrección del estado/texto en este escenario.

## 6) Tabla de diagnóstico

| Eje | Estado actual | Debería pasar | Evidencia | Impacto | Severidad | Archivo / función | Hipótesis | Recomendación |
|---|---|---|---|---|---|---|---|---|
| planner.status vs executor.status | `plan -> clarify` permitido | `plan -> deliver` obligatorio salvo excepción explícita | Lógica de contrato/eval permite clarify | Replanificación/consulta meta en turno de ejecución | Crítica | `guards/output.py::_planner_contract_signals`, `flow_config.py::_evaluate_stub` | A confirmada | Endurecer contrato y enforcement |
| must_include | No validado semánticamente | Debe aparecer realización equivalente | Sin checker textual/semántico pos-executor | Omisión de contraoferta decidida | Crítica | pipeline pos-executor | D confirmada | Agregar validador contractual |
| must_avoid | No validado | Debe bloquear/reescribir violaciones | Sin regla específica | Preguntas/meta no bloqueadas | Alta | guardrails output | D confirmada | Regla crítica configurable |
| max_questions | No enforcement | Si 0, cero preguntas | Sin contador/regex contractual | Hace preguntas contra plan | Alta | guardrails output | A/D confirmada | Constraint checker |
| role fidelity | No enforcement específico | Hablar a interlocutor final | Sin detector de “copiloto/meta” robusto | Tono de operador | Alta | prompt+guardrail | A/D confirmada | Detector lingüístico + rewrite |
| operator/meta language | Solo términos internos genéricos | Bloquear lenguaje de operador | Cobertura parcial | Meta-preguntas pasan | Alta | policy/output guardrail | D confirmada | Diccionario + regla crítica |
| bypass histórico executor | No evidencia de bypass en optimizador auditado | n/a | `run_sandbox_turn -> run_negotiation_cognitive_turn` | Hipótesis de bypass optimizador no soportada aquí | Media | `optimizador/services.py` | B parcialmente descartada | Verificar periodos previos fuera repo si aplica |
| avatar vs optimizador final text path | Ambos convergen en core cognitivo para negociación | n/a | `/negociar` y sandbox desembocan en same core | Mismo fallo potencial | Alta | `api/app.py`, `pipeline.py`, `services.py` | C confirmada (propagación) | Corregir núcleo, no solo UI |
| shared runtime vs shared backend path | Runtime compartido + endpoint único | n/a | tests de paridad | Propaga conducta entre UIs | Alta | `shared/chat_runtime.js`, tests parity | C confirmada | Mantener single path + endurecer contrato |
| validación de schema | Estructural, no semántica | Contractual completa | `_call_structured` valida forma | Pasa JSON correcto pero táctica incorrecta | Crítica | `flow_config.py::_call_structured` | A/D confirmada | post-validator de plan fidelity |
| fallback behavior | Fallback genérico no táctico | Fallback fiel al plan | `_executor_fallback` genérico | Respuestas blandas/no negociadoras | Media | `flow_config.py::_executor_fallback` | D confirmada | fallback template-aware |
| post-processing after executor | Guardrail observe-only en no críticos | Enforce para violaciones contractuales | docstring + enforcement action | No corrige desalineación | Alta | `guards/output.py` | D confirmada | elevar a crítico planner-contract |

## 7) Veredicto final

1. **Causa raíz principal**: brecha de contrato en última milla (executor + validación/guardrails) que permite y no corrige desviaciones tácticas severas pese a planner correcto.
2. **Causas secundarias**:
   - schema y validación centrados en forma JSON, no fidelidad al plan,
   - guardrail contractual incompleto (`plan->clarify` no es violación),
   - enforcement observe-only para reglas no críticas.
3. **Desde cuándo**:
   - la permisividad `plan->clarify` está presente al menos desde los commits históricos que introducen esa lógica en `flow_config` / guardrails (auditado por blame y código actual), y no emerge en `a1939b2`.
4. **Impacto**: respuestas meta, preguntas indebidas, pérdida de ejecución táctica, degradación percibida de calidad negociadora.
5. **Qué arreglar primero (mínimo viable)**:
   - (P0) invalidar `plan->clarify` salvo bandera explícita de excepción,
   - (P0) validador contractual post-executor (`must_include`, `must_avoid`, `max_questions`, role fidelity),
   - (P1) convertir violaciones contractuales en regla crítica con rewrite/block controlado,
   - (P1) fallback executor guiado por `planner_output.content_plan`.

## 8) Nivel de confianza

**Alto** para la causa principal (evidencia directa en código + tests diagnósticos).
**Medio** para atribución temporal fina exacta de primera aparición percibida (faltan trazas de producción antiguas en este repo para pin-point operacional).
