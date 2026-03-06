> Estado: histórico. Este diagnóstico fue previo a la migración a Sessions en `backend/negociacion/agents_pipeline.py`.

# Diagnóstico de memoria en `negociacion` (Sessions / trimming / summarization)

## Estado actual (resumen ejecutivo)

- **Sí** existe una estrategia híbrida de memoria: recorte por turnos + resumen sintético cuando se supera un umbral.
- **No** se está usando **OpenAI Agents SDK Session** (`SessionABC`, `Runner.run(..., session=...)`) de forma nativa.
- **Sí** se está usando Responses API con una capa de memoria propia (`SessionMemoryManager`) implementada en el proyecto.

## Evidencia técnica

1. `negociacion` delega en un pipeline 3-LLM (`summarizer -> planner -> executor`).
2. La memoria se maneja con `SessionMemoryManager`, no con `openai-agents`.
3. El algoritmo actual resume el prefijo antiguo e inyecta:
   - `user`: "Summarize the conversation we had so far."
   - `assistant`: `{summary}`
4. Se conservan los últimos `keep_last_n_turns` turnos reales (configurados en 3) y se activa al superar `context_limit` (6).
5. Los prompts de `negociacion` están en placeholder (`prompt pendiente de pegar`), por lo que la calidad real de summarization/planning/execution depende de prompts fallback genéricos del engine.

## Comparación con la filosofía del cookbook de OpenAI

Coincidencias:
- Patrón híbrido trimming + summarization.
- Inserción de bloque sintético user/assistant para continuidad.
- Separación de responsabilidades entre resumen, planificación y respuesta final.

Brechas para quedar “exactamente” igual al enfoque recomendado:
- No usar `Session` del Agents SDK (es una implementación custom).
- No hay compresión estructurada estricta con secciones fijas en `negociacion` por falta de prompt definitivo.
- Falta observabilidad explícita de calidad de summary (métricas/evals dedicadas).
- El recorte de payloads de herramientas no está especializado para tool outputs extensos.

## Recomendación para `negociacion`

Para replicar la filosofía técnica y estratégica de OpenAI con mayor fidelidad:

1. **Definir prompt de resumen estructurado** en `backend/negociacion/prompts/summarizer_prompt.txt` con secciones fijas (entorno, estado, hitos, bloqueos, siguiente paso, contradicciones, UNVERIFIED).
2. **Añadir evaluaciones de memoria** (regresión):
   - retención de constraints,
   - no contradicción,
   - precisión de IDs/fechas,
   - no repetición innecesaria.
3. **Mantener híbrido actual** (ya implementado) pero con tuning por dominio negociación:
   - `context_limit` y `keep_last_n_turns` según distribución real de conversaciones.
4. **Opcional (si se busca equivalencia literal):** migrar la capa custom a `openai-agents` Session (manteniendo misma lógica de negocio).

## Veredicto

- **Hoy no está implementado “exactamente” como el ejemplo del Agents SDK**, pero
- **sí está implementada la misma filosofía base** (trimming + summarization + últimos turnos verbatim) en una arquitectura propia.
