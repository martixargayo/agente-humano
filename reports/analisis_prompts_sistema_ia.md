# Análisis de prompts del sistema de IA

## Alcance revisado
Se revisaron los prompts runtime principales y su documentación literal para el pipeline semántico de negociación:
- `SUMMARY_*` (memoria larga).
- `WORLD_JUDGE_V4` (ledger semántico).
- `PLANNER_SEMANTIC_V1` (plan táctico por fase).
- `EXECUTOR_V2` y `EXECUTOR_FINALIZER_V1` (redacción final + post-procesado).

## Lectura arquitectónica
El sistema usa una arquitectura por capas con contratos estrictos por rol:
1. **Summarizer** consolida memoria larga con formato fijo y reglas de privacidad.
2. **World Judge** mantiene un ledger táctico semántico de 3 listas con política de no-op.
3. **Planner** decide fase/estilo/movimiento con control de transición y prioridad HUMAN-FIRST.
4. **Executor** materializa el plan con guardrails de canal y agencia.
5. **Finalizer** hace control de calidad final de brevedad/coherencia/esquema.

Este diseño reduce el acoplamiento entre “entender contexto”, “decidir estrategia” y “redactar”.

## Fortalezas observadas

### 1) Contratos de salida muy claros
Se exige JSON estricto y sin claves extra en judge/planner/executor/finalizer, lo que facilita parseo robusto y retries deterministas.

### 2) Buenas defensas contra drift de rol
Hay múltiples reglas que fuerzan personaje en escena (Carlos comprador), evitan “assistant talk” y prohíben meta-explicaciones.

### 3) Memoria táctica bien separada
El `semantic_ledger` captura ideas accionables a nivel semántico (no literal), mientras el resumen largo conserva continuidad estratégica y límites.

### 4) Privacidad explícita del comprador
La memoria larga evita persistir techo/presupuesto/BATNA/MAPAN, sustituyéndolo por placeholders de seguridad.

### 5) Diseño orientado a no repetición
La combinación `lo_que_ya_pregunte` + `lo_que_falta_pero_no_insistire` + políticas NO-REPEAT reduce repreguntas y desgaste conversacional.

## Riesgos / áreas a mejorar

### 1) Complejidad alta y potenciales tensiones internas
Hay muchas reglas “hard” simultáneas (human-first, no repetir, no preguntar por defecto, progresar cada turno, control de fase). En casos ambiguos podría haber competencia entre objetivos.

### 2) Riesgo de deriva documental
Existen prompts en runtime (`backend/prompts.py`) y artefactos literales en `docs/prompts_literal_v2`; si no se sincronizan de forma automática, puede aparecer drift entre lo documentado y lo ejecutado.

### 3) Costo de tokens
Los prompts de planner/executor son extensos; en producción esto puede afectar latencia/costo, especialmente si se procesan conversaciones largas con contexto adicional.

### 4) Dependencia de heurísticas semánticas
Reglas como “detectar cierre de tema”, “no-op recomendado” o “rapport on_topic” son potentes, pero sensibles al modelo y a matices lingüísticos.

## Recomendaciones concretas
1. **Agregar scorecards automáticos por turno** (cumplimiento de 5–8 invariantes críticos), para detectar regresiones tempranas.
2. **Consolidar source-of-truth**: mantener prompts en un solo lugar y generar artefactos docs/literales automáticamente.
3. **Compactar prompts**: mover bloques explicativos largos a reglas mínimas más verificadores externos.
4. **Matriz de conflictos de reglas**: definir prioridad explícita en casos límite (ej. responder pregunta personal vs empujar progreso negociador).
5. **Observabilidad semántica**: guardar métricas de `no_update`, repreguntas evitadas, violaciones de canal y tasa de retries por schema.

## Diagnóstico ejecutivo
En general, los prompts muestran un **diseño maduro, con contratos fuertes y foco en estabilidad conversacional** para un agente negociador roleplay. El principal riesgo no es la falta de guardrails, sino su **densidad**: conviene invertir en simplificación operativa y telemetría de cumplimiento para sostener calidad a escala.
