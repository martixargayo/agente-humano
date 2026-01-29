# WHY: Cambios 2026 en negociación (robustez y verificabilidad)

## Problema
- Falsos positivos: flags activados sin evidencia real y confusiones entre plazo vs urgencia.
- Intents “pegadas”: progreso aparente sin evidencia nueva, loops y replans abruptos.
- Guardrails frágiles: validadores que disparaban por números irrelevantes (km/año/cv).
- Policies sin contrato ejecutable: required_inputs ambiguos y planner sin trazabilidad.

## Cambio
- **Evidencia por field + recency bias**: EvidenceItem ahora incluye field/polarity/span; se deduplica por clave semántica y los flags se derivan por campo con sesgo a la evidencia más reciente.
- **Observación vs derivado**: se guarda `world_observations` con señales crudas y `world_derived` con flags consumibles; los campos legacy se mantienen pero se recalculan desde evidencia.
- **Calibración por tipo**: umbrales diferenciados por PRICE/FIRMNESS/DEADLINE/URGENCY con defaults ajustables vía env.
- **Progreso real en intents**: progreso por delta de slots o evidencia nueva del target_slot; replan a cierre solo con precio + firmeza fuerte.
- **Planner con contrato y trazabilidad**: required_inputs tipados, inputs_used validado contra keys existentes y prompt reforzado.
- **Validator contextual**: números solo cuentan si están en contexto de precio; reparación revalida y cae a fallback seguro si persiste.

## Ajustes recientes (tono, dedupe y progreso)
- **Tono respetando heurísticos**: el derivador ya no resetea `tone_signal`/`tone_confidence` a defaults si no hay evidencia fuerte, evitando falsos neutrales cuando el regex detecta cordialidad o tensión.
- **Dedupe también en LLM**: la misma política de deduplicación por clave semántica aplica a evidencia generada por LLM, evitando inflar memoria y sesgos por repetición.
- **Progreso por evidencia real**: los intents avanzan solo si hay nuevas claves de evidencia asociadas al slot, no por flips derivados debidos a umbrales o recency.

## Impacto
- Menos replans bruscos y menos loops por “progreso fantasma”.
- Guardrails con enforcement real sin falsos positivos por números irrelevantes.
- Planner más trazable y consistente con contractos de policy.

## Tradeoffs
- Mayor complejidad y más tests, pero comportamiento más verificable y explicable.

## Compatibilidad
- Consumers legacy intactos: se mantienen los campos de WorldState; ahora se derivan desde evidencia.

## WHY: World evidence v2 (open-set controlado)
- **Closed-world antes**: EvidenceItem dependía de enums (`EvidenceType`, `_FIELD_TO_TYPE`) y del acoplamiento field->type, obligando a tocar core por cada nueva señal.
- **Whitelist + cuarentena**: el registry de paths limita lo que puede entrar; todo path no registrado se captura en `unknown_claims` para trazabilidad sin contaminar consumidores.
- **Source-of-truth unidireccional**: `world_observations_v2` es la fuente y los flags/evidence legacy se derivan de forma determinista, evitando drift.
- **Dedupe determinista + caps**: dedupe por `path|polarity|bucket|text` y límites de memoria (`MAX_CLAIMS`, `RECENT_K`, `MAX_UNKNOWN`) mantienen rendimiento y evitan sesgos por repetición.
- **Tradeoffs**: aumenta la complejidad del updater/validación, pero habilita extensibilidad open-set y auditoría consistente.
- **Plan Fase B**: migrar consumidores a queries v2 y mover reglas de flags a un engine declarativo por dominio.
