# 00 · Resumen ejecutivo — propuesta `conversacion_simple`

## Qué se quiere construir

Crear un **nuevo flujo real** llamado `conversacion_simple` que conserve la robustez operacional del sistema actual (sesión stateful, contrato de contexto, trazas, superficies, contextos oficiales y presentation), pero con una diferencia crítica: **el camino online de cada turno usa una sola LLM**.

## Por qué

El flujo `negociacion` actual ejecuta 4 llamadas online por turno (`memory`, `phase_classifier`, `planner`, `executor`) en un pipeline contractual robusto. Esto da modularidad, pero aumenta latencia/coste/complejidad. La meta de `conversacion_simple` es reducir esa complejidad en runtime sin sacrificar coherencia sistémica.

## Qué cambia vs `negociacion`

- Cambia el runtime online de turno: de 4 LLMs a 1 LLM.
- Cambia el contrato de salida del “cerebro único” para incluir:
  - respuesta final al usuario,
  - artefactos estructurados para actualizar estado/memoria/fase (si aplica).
- Se rediseña la responsabilidad de `memory`, `phase_classifier` y `executor` para que queden absorbidas por un único nodo lógico.

## Qué NO cambia (principio de mínima ruptura)

- Modelo stateful de sesiones, locks y TTL.
- Contrato de contexto (resolver, binding, public mapping, prevalidación y `execute_turn_with_contract`).
- Filosofía de contextos oficiales por carpeta + manifest + assets.
- Integración con superficies (`interfaz_usuario`, `optimizador`, legacy mientras exista).
- Estructura de trazabilidad y metadatos contractuales por turno.
- Capa de presentation contextual.

## Recomendación final (resumen)

1. **Sí conviene crear `conversacion_simple` como flujo real nuevo**, no como simple contexto de `negociacion`, porque la topología de pipeline (1 LLM) cambia semántica de contratos de nodo y de trazas.
2. Reusar al máximo los cimientos transversales: sesiones, contexto, `execute_turn_with_contract`, puentes HTTP de errores, locking/TTL, mapping de contextos públicos, presentation resolver y tooling de optimizador.
3. Introducir un runtime nuevo con **nodo único** (provisionalmente `brain`) que devuelva contenido + estado en una respuesta estructurada.
4. Mantener memoria operativa con doble estrategia:
   - online: trimming determinista + actualización mínima por la salida del nodo único,
   - compresión histórica: preferentemente **diferida** (fuera del camino crítico) y con fallback determinista.

## Contextos iniciales solicitados

Para `conversacion_simple`, arrancar con dos contextos oficiales:
- `baseline`
- `negociacion_sala_reuniones`

Ambos deben ser **idénticos en contrato y comportamiento** en esta fase (diferencias solo como roadmap futuro).

## Decisión más delicada

La decisión más sensible es dónde ubicar la **compresión/summarization histórica** sin reintroducir multi-LLM online:
- inline en la única llamada,
- diferida async,
- determinista,
- o híbrida.

La recomendación de esta propuesta es un esquema híbrido con prioridad a **compresión diferida** para no romper el objetivo principal (1 LLM en el camino crítico del turno).
