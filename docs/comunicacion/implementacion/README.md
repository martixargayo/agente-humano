# Comunicación — diseño técnico ejecutable (fase 2)

## Resumen ejecutivo

Esta segunda fase aterriza el diagnóstico inicial de `docs/comunicacion/` a una capa **lista para convertirse en tareas de implementación**. No implementa código funcional, pero sí fija una propuesta concreta de:
- árbol de archivos,
- módulos nuevos,
- archivos actuales a tocar,
- rutas HTTP exactas,
- firmas de funciones,
- contratos JSON,
- entidades persistentes,
- secuencias de flujo,
- snippets orientativos alineados con el estilo real del repo,
- y un MVP cerrable sin contaminar el dominio `negociacion`.

La línea maestra se mantiene: `comunicacion` será un flujo totalmente separado de `negociacion`, con:
- namespace backend propio,
- app pública propia,
- surface propia,
- bundle de evaluación propio,
- report propio,
- y uso selectivo de infraestructura transversal ya existente.

## Decisiones consideradas suficientemente cerradas

1. **Dominio nuevo**: `comunicacion` no entra en `backend/negociacion`; tendrá namespace propio.
2. **Surface nueva**: no se recomienda reutilizar `/api/interfaz_usuario` ni `backend/interfaz_usuario_app/` como host principal del flujo.
3. **Contrato de evaluación nuevo**: no se reutilizan `FeedbackInputBundleV1`, `DomainContext` ni `UiFeedbackReportV1` tal cual.
4. **Sesión ligera**: el vídeo y los derivados no deben almacenarse dentro de `SessionState`; la sesión solo guarda referencias activas.
5. **MVP de media realista**: el primer corte debe centrarse en `recording` + transcript + métricas audio mínimas + report básico; gesticulación avanzada puede quedar desacoplada para una iteración posterior.
6. **Embed reutilizable**: el mecanismo de `final_result` / `final_result_saved` actual es la base para Moodle/cuaderno.

## Qué queda fuera del MVP

- scoring fino y metodología cerrada de pausas/entonación/gesticulación,
- análisis visual avanzado frame a frame con criterios definitivos,
- storage binario distribuido definitivo,
- reingesta masiva de attempts históricos,
- edición avanzada del vídeo en frontend,
- workflows de reentrega o múltiples intentos evaluados en paralelo,
- generalización grande del sistema de sesiones más allá de lo imprescindible.

## Versión mínima viable recomendada

La versión mínima viable que este diseño propone dejar lista para una fase de implementación posterior es:

1. **Bootstrap de sesión**
   - `POST /api/comunicacion/sessions/bootstrap`
   - crea/rehidrata identidad, fija surface y contexto `comunicacion`, devuelve `capture_policy`.

2. **Create attempt**
   - `POST /api/comunicacion/attempts`
   - genera `attempt_id` ligado a la sesión.

3. **Upload recording**
   - `POST /api/comunicacion/attempts/{attempt_id}/upload`
   - registra una grabación de vídeo+audio y devuelve `recording_id` + poster opcional.

4. **Crear evaluación**
   - `POST /api/comunicacion/attempts/{attempt_id}/submit`
   - crea `evaluation_id` y dispara job.

5. **Generar report básico**
   - job con transcript + audio features mínimas + bloque de media + recomendaciones básicas.

6. **Mostrar vídeo + informe**
   - app pública nueva renderiza reproductor de vídeo y `UiCommunicationReportV1`.

### MVP exacto recomendado

**Sí entra en MVP**
- surface nueva `/comunicacion` + `/api/comunicacion`
- `attempt_id`, `recording_id`, `evaluation_id`
- transcript segmentada
- rasgos mínimos de audio: duración, speech rate, silencios básicos
- report con 3–4 bloques básicos
- integración embed final con `video_ref` + `payloadjson`

**No entra en MVP**
- gesture scoring fino
- modelos visuales sofisticados
- chunked upload
- storage definitivo no volátil si bloquea la primera iteración
- comparación entre múltiples intentos

## Orden recomendado de implementación futura

1. surface + router + bootstrap
2. attempt repository + recording repository mínimo
3. upload y persistencia de refs
4. evaluación mínima (transcript + audio features básicas)
5. assembler y report frontend
6. embed final con vídeo + informe
7. análisis visual/gesticulación de segunda fase
8. endurecimiento de storage y persistencia histórica

## Índice de documentos

- [01-backend-y-rutas.md](./01-backend-y-rutas.md)
- [02-pipeline-recording-y-artefactos.md](./02-pipeline-recording-y-artefactos.md)
- [03-ui-captura-api-y-estados.md](./03-ui-captura-api-y-estados.md)
- [04-evaluacion-y-report.md](./04-evaluacion-y-report.md)
- [05-cambios-transversales-y-riesgos.md](./05-cambios-transversales-y-riesgos.md)

## Archivos del repo inspeccionados para esta fase

### App / surfaces / servicios
- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_resolver.py`

### Sesiones y runtime transversal
- `backend/sessions/state.py`
- `backend/sessions/lifecycle.py`
- `backend/sessions/surface_scope.py`
- `backend/sessions/session_lock.py`

### Evaluación actual
- `backend/evaluacion/contracts/models.py`
- `backend/evaluacion/api/router.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/assembler.py`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/evaluacion/domains/negotiation/context_resolver.py`
- `backend/evaluacion/storage/models.py`
- `backend/evaluacion/storage/in_memory_repository.py`

### Frontend / embed / report
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/tests/test_public_interfaz_usuario_serving.py`
- `backend/tests/test_embed_final_result_contract.py`

### Documentación fase 1
- `docs/comunicacion/README.md`
- `docs/comunicacion/bloque-a-arquitectura.md`
- `docs/comunicacion/bloque-b-pipeline-y-estado.md`
- `docs/comunicacion/bloque-c-ui-y-embed.md`
- `docs/comunicacion/bloque-d-informe-y-feedback.md`

## Recomendación final

Esta segunda capa debe entenderse como el **puente directo entre diagnóstico y codificación**. La siguiente fase de trabajo ya no necesitaría redefinir arquitectura base: bastaría con convertir estos documentos en tareas de implementación discretas y ordenadas.
