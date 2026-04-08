# 10 · Riesgos, decisiones abiertas y preguntas

## 1) Riesgos técnicos principales

1. **Acoplamiento de naming a `negociacion`**
   - Riesgo: duplicación o hacks en runtime nuevo.
2. **Trace schema rígido a 4 nodos**
   - Riesgo: tooling roto o inconsistente en optimizador.
3. **Compresión histórica insuficiente**
   - Riesgo: pérdida de contexto en conversaciones largas.
4. **Compresión histórica excesiva**
   - Riesgo: deriva semántica y respuestas incoherentes.
5. **Cambio de flujo sin contrato unificado**
   - Riesgo: drift entre IU y optimizador.

## 2) Decisiones abiertas (requieren validación humana)

1. Selección de flujo por contexto vs parámetro explícito en APIs.
2. Grado de compatibilidad de trace entre flujos.
3. Mantener o no el concepto de fase en `conversacion_simple`.
4. Política exacta de compresión diferida (trigger, frecuencia, SLA).
5. Estrategia de rollout (flag por sesión, contexto o superficie).

## 3) Trade-offs relevantes

## 3.1 Reuso máximo vs limpieza arquitectónica

- Reuso máximo reduce riesgo inmediato.
- Limpieza mayor reduce deuda a largo plazo.

## 3.2 1-LLM estricto vs calidad de memoria

- 1-LLM estricto minimiza latencia/coste.
- memoria de alta fidelidad puede requerir trabajo diferido o heurísticas avanzadas.

## 3.3 Compatibilidad total de contratos vs evolución de schema

- Compatibilidad total facilita adopción.
- evolución puede ser necesaria para representar `brain` correctamente.

## 4) Respuestas explícitas a las 10 preguntas solicitadas

### 1. ¿Nuevo flujo real o variante/contexto de `negociacion`?

**Recomendación:** nuevo flujo real (`conversacion_simple`).

### 2. Si queremos idéntico por fuera con pipeline 1-LLM, ¿qué abstraer?

- config/runtime adapters por flujo,
- trace envelope común,
- selección de contexto flow-aware.

### 3. ¿Dónde están los mayores acoplamientos a `negociacion`?

- `flow_config.py` monolítico,
- naming/state keys `negotiation_*`,
- shape de traces y tests orientados a 4 nodos.

### 4. ¿Cómo mantener estado canónico coherente con una sola LLM?

- salida estructurada estricta + aplicación determinista + validación pydantic + trazas de patch.

### 5. ¿Cómo mantener trimming + summarization sin volver a 4 LLMs por turno?

- 1 LLM online + compresión diferida + fallback determinista.

### 6. ¿Cómo soportar IU y optimizador sin drift?

- reusar `execute_turn_with_contract` y capa común de sesión/contexto/trazas; adaptar solo runtime interno.

### 7. ¿Qué pruebas demuestran que `baseline` y `negociacion_sala_reuniones` son idénticos?

- tests de manifest, assets schema, prompts contractuales, mapping y e2e comparativo.

### 8. ¿Qué parte queda tal cual y cuál desacoplar antes?

- tal cual: lifecycle/locks/context contract.
- desacoplar: runtime monolítico, naming fijo de estado/trazas.

### 9. ¿Recomendación final de diseño y por qué?

- nodo único `brain` + contratos sistémicos reutilizados + memoria híbrida online/offline.

### 10. ¿Decisión más delicada?

- política de compresión histórica (calidad vs latencia vs pureza 1-LLM).

## 5) Recomendaciones accionables inmediatas (sin implementar)

1. Acordar ADR de topología `single_llm`.
2. Congelar `BrainOutput.v1` antes de tocar código.
3. Definir tests de equivalencia de contextos iniciales.
4. Definir métricas de éxito (latencia/coste/calidad/errores de contrato).
