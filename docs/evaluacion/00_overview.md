# 00 — Overview

## Qué es este subsistema

El subsistema de evaluación de desempeño mide **cómo negoció el usuario**, no cómo respondió el agente. Se ejecuta al cerrar una conversación (`Finalizar conversación`) y genera un informe visual estructurado.

Se diseña para convivir con la arquitectura actual de negociación ya existente:

- endpoint de turno activo (`/negociar` y superficie parity-safe `/api/interfaz_usuario/negociacion/turn`),
- estado canónico fuerte (`negotiation_canonical`) con contratos Pydantic `extra="forbid"`,
- pipeline multi-nodo (`memory`, `phase_classifier`, `planner`, `executor`),
- guardrails de entrada/salida,
- trazas por turno con artefactos de prompt y metadata de modelos,
- infra de evals/datasets ya separada por capas fixture/live.

## Problema que resuelve

Hoy el sistema decide y responde turno a turno, pero no entrega un **informe final estructurado** de desempeño del usuario. El producto necesita:

1. cierre explícito de sesión,
2. evaluación asíncrona con estado de proceso,
3. informe visual con bloques puntuables, trayectoria por turnos y recomendaciones accionables.

## Objetivos de v1

1. Introducir un workflow asíncrono de evaluación con jobs y polling.
2. Definir contratos versionados y estrictos:
   - `feedback_input_bundle_v1` (código),
   - `feedback_report_core_v1` (LLM 1),
   - `turn_trajectory_v1` (LLM 2),
   - `ui_feedback_report_v1` (ensamblado backend).
3. Mantener separación análisis/presentación.
4. Reusar patrones del repo (prompts en archivo, validación estricta, trazabilidad).
5. Dejar base extensible a otras soft skills además de negociación.

## Alcance v1

Incluye:

- contratos y versionado,
- orquestación de job,
- runners de 2 evaluadores LLM,
- ensamblado backend a contrato UI,
- persistencia separada del canonical state,
- endpoints para iniciar evaluación y consultar estado/resultado,
- integración frontend mínima con modal + loading + pantalla informe.

No incluye:

- recalibración automática online de rúbricas,
- infraestructura de cola distribuida obligatoria (se propone abstracción compatible),
- soporte completo para todos los dominios (v1 implementa negociación, deja interfaz para otros).

## No-objetivos (explícitos)

- No rehacer pipeline cognitivo de negociación.
- No embutir el informe final como bloque interno del `CanonicalState` de negociación.
- No resolver todo con una LLM monolítica.
- No mezclar texto libre no estructurado como output principal.

## Relación con negociación actual

El evaluador se conecta a artefactos ya existentes de negociación:

- `world_state["negotiation_canonical"]` para estado final,
- `world_state["negotiation_canonical_recent_dialogue"]` para ventana corta,
- `world_state["negotiation_canonical_traces"]` para trazabilidad profunda por turno,
- `history` de sesión para reconstrucción completa de la conversación.

Con esto, v1 evita modificar comportamiento de `run_negotiation_cognitive_turn` y opera como subsistema posterior al cierre.

## Suposiciones de diseño

1. **La sesión permanece disponible en memoria** el tiempo suficiente para construir el bundle (coherente con `SESSIONS` en RAM).
2. **La UI principal de cierre estará en `/interfaz_usuario`** (la superficie activa parity-safe), aunque `/negociar` legacy se puede adaptar después.
3. **El resultado final del job se persiste separado** en nuevo storage de feedback, con referencia `(user_id, session_id, evaluation_id)`.
