# Comunicación — diagnóstico técnico del repositorio

## Resumen ejecutivo

Este bloque documental describe cómo incorporar un nuevo flujo `comunicacion` en este repositorio sin contaminar el flujo maduro de `negociacion`. La conclusión principal es que `comunicacion` debe modelarse como **actividad de primera clase**, con **surface propia**, **contextos propios**, **pipeline de captura/procesado propio** y **evaluación propia**, reutilizando únicamente la infraestructura transversal ya estabilizada: app FastAPI, sesiones, TTL/locks, patrón de contextos oficiales, pipeline de jobs de feedback, ensamblado de reports y bridge embed con Moodle.

La evidencia del repositorio muestra que `negociacion` ya está desacoplada por varias capas: contexto oficial + slug público, binding de contexto en sesión, superficie `interfaz_usuario`, evaluación asíncrona y contrato embed de resultado final. Eso hace viable replicar el patrón para `comunicacion`, siempre que se mantenga la separación de dominio y no se intente forzar el nuevo flujo dentro de `backend/negociacion` ni dentro de los contratos actuales de `evaluacion` diseñados solo para negociación.

## Documentos

### Capa 1 — Diagnóstico base
- [Bloque A — Arquitectura y encaje en la repo](./bloque-a-arquitectura.md)
- [Bloque B — Pipeline de datos y estado interno](./bloque-b-pipeline-y-estado.md)
- [Bloque C — UI de captura + embed + experiencia](./bloque-c-ui-y-embed.md)
- [Bloque D — Informe final / ensamblado de feedback](./bloque-d-informe-y-feedback.md)

### Capa 2 — Diseño técnico ejecutable
- [Implementación — índice](./implementacion/README.md)
- [01 — Backend y rutas](./implementacion/01-backend-y-rutas.md)
- [02 — Pipeline recording y artefactos](./implementacion/02-pipeline-recording-y-artefactos.md)
- [03 — UI de captura, API y estados](./implementacion/03-ui-captura-api-y-estados.md)
- [04 — Evaluación y report](./implementacion/04-evaluacion-y-report.md)
- [05 — Cambios transversales y riesgos](./implementacion/05-cambios-transversales-y-riesgos.md)

### Capa 3 — Plan de implementación en 6 fases
- [Plan 6 fases — índice](./plan_6_fases/README.md)
- [Fase 1 — Cimientos de arquitectura, surface y bootstrap](./plan_6_fases/fase-1.md)
- [Fase 2 — Attempt, recording y repositorio mínimo](./plan_6_fases/fase-2.md)
- [Fase 3 — App pública de captura](./plan_6_fases/fase-3.md)
- [Fase 4 — Evaluación mínima y pipeline de job](./plan_6_fases/fase-4.md)
- [Fase 5 — Informe final, renderer y exportables](./plan_6_fases/fase-5.md)
- [Fase 6 — Endurecimiento, embed final y compatibilidad lógica con Moodle](./plan_6_fases/fase-6.md)

## Decisiones cerradas

1. `comunicacion` no debe modelarse como contexto de `negociacion`.
2. Debe existir un **nuevo dominio** de backend con módulos y contratos propios.
3. Debe existir una **surface pública distinta** de la negociación, aunque pueda convivir bajo la misma app FastAPI.
4. Debe existir un **bundle de evaluación nuevo**, porque el contrato actual `FeedbackInputBundleV1` y `DomainContext` solo cubren negociación conversacional.
5. El sistema actual de sesiones, TTL, locks, `surface_scope`, jobs asíncronos y embed final **sí debe reutilizarse** como base.
6. El report visual actual sirve como **referencia fuerte**, pero no como contrato final reutilizable sin cambios, porque hoy su semántica está centrada en bloques de negociación y trayectoria por turnos.

## Decisiones pendientes

1. **Persistencia real de media**: el repositorio actual guarda sesiones y reports en memoria/Redis, pero no dispone de una capa de almacenamiento de vídeos ni artefactos binarios.
2. **Preprocesado audiovisual**: queda abierta la decisión entre pipeline interno Python, workers externos o proveedor especializado para extraer frames, diarización temporal, prosodia y señales visuales.
3. **Nivel de multimodalidad**: está pendiente decidir si la evaluación visual de gesticulación será heurística/preprocesada o directamente LLM/VLM-based.
4. **Contrato exacto con Moodle/cuaderno**: el embed actual cubre entrega de informe final; queda por cerrar si el vídeo se entregará como URL persistente, referencia opaca, asset firmada o duplicado parcial de metadatos.
5. **App pública nueva vs variante fuerte de la actual**: el diagnóstico recomienda surface/app nueva para no mezclar semánticas, pero la decisión final depende del grado de reutilización visual deseado.
6. **Versionado de esquemas**: está pendiente definir si `comunicacion` vive dentro de `evaluacion/contracts/models.py` o en un namespace paralelo (`evaluacion/contracts/communication_models.py`).

## Riesgos técnicos

### Riesgos altos
- El `SessionSurface` actual solo admite `'optimizador'` e `'interfaz_usuario'`; añadir `comunicacion` exige extender este contrato o crear uno paralelo.
- `DomainContext` y `FeedbackInputBundleV1` están tipados literalmente para `domain="negociacion"`; intentar reutilizarlos directamente introduciría deuda y branching frágil.
- El repositorio no tiene una capa general de storage binario; introducir vídeo sin diseñar esa capa rompería la trazabilidad y la revisualización posterior.
- El frontend actual está muy acoplado al flujo negociación+feedback; mezclar captura de vídeo con esa app incrementaría mucho el estado mutable y el riesgo de regresión.

### Riesgos medios
- El bridge embed actual entrega `final_result` y ACK correlacionado, pero no está claro todavía cómo se anexaría un vídeo reproducible o un puntero persistente al cuaderno.
- El pipeline de evaluación actual usa un `ThreadPoolExecutor` en proceso y repositorio en memoria; para media pesada podría quedarse corto incluso como primera fase.
- La presentación actual (`PresentationConfig`) está muy orientada a avatar/fondo/voz; podría no ser suficiente para una activity shell centrada en cámara y revisión de toma.

## Referencias al código actual inspeccionado

### App y routing
- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`

### Contextos y binding
- `backend/negociacion/contexts/resolver.py`
- `backend/negociacion/contexts/models.py`
- `backend/negociacion/contexts/public_mapping.py`
- `backend/negociacion/contexts/session_binding.py`

### Sesiones e infraestructura transversal
- `backend/sessions/state.py`
- `backend/sessions/lifecycle.py`
- `backend/sessions/surface_scope.py`
- `backend/sessions/session_lock.py`

### Evaluación actual
- `backend/evaluacion/api/router.py`
- `backend/evaluacion/contracts/models.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/assembler.py`
- `backend/evaluacion/engine/flow_config.py`
- `backend/evaluacion/domains/negotiation/extractor.py`
- `backend/evaluacion/domains/negotiation/context_resolver.py`
- `backend/evaluacion/storage/models.py`
- `backend/evaluacion/storage/in_memory_repository.py`

### Frontend y embed
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/tests/test_public_interfaz_usuario_serving.py`
- `backend/tests/test_embed_final_result_contract.py`

### Tests de arquitectura y multicontexto
- `backend/tests/test_phase6_evaluation_context_aware.py`
- `backend/tests/test_phase8_second_official_context.py`
- `backend/tests/test_phase8_second_official_context_e2e_http.py`

## Recomendación global

El repo ya tiene suficiente infraestructura para soportar `comunicacion`, pero la clave es **no reusar por conveniencia piezas tipadas semánticamente para negociación**. La forma más limpia es:

- nuevo namespace de dominio (`backend/comunicacion`),
- nueva surface pública y router,
- nuevo binding/context resolver,
- nuevos contratos de evaluación y report,
- nueva app de captura o shell frontend separada,
- y reaprovechamiento selectivo de sesiones, jobs, embed y utilidades de report.
