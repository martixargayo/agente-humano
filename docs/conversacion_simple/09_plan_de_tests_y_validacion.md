# 09 · Plan de tests y validación para `conversacion_simple`

## 1) Objetivo de validación

Demostrar que `conversacion_simple` mantiene robustez sistémica (contratos/contextos/sesiones/superficies) con pipeline 1-LLM.

## 2) Unit tests

1. parser/validación de `BrainInput` y `BrainOutput`.
2. aplicación determinista de `state_patch`.
3. trimming de recent dialogue.
4. fallback determinista de compresión.

## 3) Tests de contrato de contexto

1. resolver de contexto oficial por flow.
2. binding de sesión + conflictos.
3. precheck de coherencia sesión/config/prompts_dir.
4. traducción HTTP de errores contractuales.

## 4) Tests de assets/contexto

1. manifest schema y required files.
2. persona/brief/phase assets parseables.
3. equivalencia contractual entre `baseline` y `negociacion_sala_reuniones`.
4. prompt mapping v1/v2 si aplica.

## 5) Tests de sesión/locks/TTL

Reusar patrones actuales:
- busy lock 423,
- retries en timeout de redis,
- lifecycle bootstrap/active/finalized,
- ownership de superficie.

## 6) Tests de memoria y compresión

Escenarios:
1. conversación corta: sin compresión.
2. conversación larga: trimming correcto y compresión activada.
3. fallo compresión diferida: fallback determinista.
4. no pérdida de facts críticos tras compresión.

## 7) Tests E2E

## 7.1 `interfaz_usuario`

- bootstrap -> turn -> finalize.
- validación de `entry_contract` y context metadata.

## 7.2 `optimizador`

- sandbox turn.
- compare turns en flujo 1-LLM.
- overrides sobre prompt único.

## 8) Comparativas `negociacion` vs `conversacion_simple`

1. latencia media por turno,
2. llamadas a modelo por turno,
3. ratio de fallos de contrato,
4. estabilidad de estado en diálogos largos,
5. calidad percibida de respuesta.

## 9) Qué trazas revisar

- `context_meta` coherente.
- `_entry_contract` correcto.
- `pipeline_topology=single_llm`.
- stage timings de único nodo.
- eventos de compresión y modo usado.

## 10) Detección de regresiones

1. golden traces por fixtures.
2. diffs de outputs estructurados.
3. alarmas por aumento de fallback/refusal.
4. alarmas por crecimiento no acotado de memoria.

## 11) Definición de “Done” de validación

- Todos los contratos críticos en verde.
- E2E en IU y optimizador en verde.
- evidencia de 1 llamada online por turno.
- resultados de compresión aceptables en dataset de conversaciones largas.
