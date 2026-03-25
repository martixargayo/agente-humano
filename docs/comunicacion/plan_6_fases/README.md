# Comunicación — plan de implementación en 6 fases

## Resumen ejecutivo del plan completo

Este bloque convierte toda la documentación previa de `docs/comunicacion/` en un **plan de implementación en 6 fases exactas**, pensado para poder ejecutarse después como prompts separados de Codex sin rediseñar la arquitectura en cada iteración.

El principio rector se mantiene sin cambios:
- `comunicacion` será un flujo nuevo y paralelo a `negociacion`,
- con **app pública propia**,
- **API propia**,
- **bundle de evaluación propio**,
- **report propio**,
- y reutilización estrictamente selectiva de infraestructura transversal ya existente.

Este plan **no implementa código funcional**. Su función es dejar fijados:
- el orden de trabajo,
- el alcance por fase,
- los archivos a crear o tocar,
- las funciones y contratos a introducir,
- los tests que deben acompañar cada fase,
- y los riesgos que cada corte reduce antes de pasar al siguiente.

## Visión general de las 6 fases

1. **Fase 1 — Cimientos de arquitectura, surface y bootstrap**  
   Se crea el esqueleto del dominio `backend/comunicacion`, el router `/api/comunicacion`, la surface pública `/comunicacion`, el binding mínimo de sesión y los contextos propios.

2. **Fase 2 — Attempt, recording y repositorio mínimo**  
   Se fijan las entidades de negocio, el repositorio MVP, el flujo create-attempt → attach-recording y el estado mínimo que sí puede vivir en sesión.

3. **Fase 3 — App pública de captura**  
   Se diseña la app estática `backend/comunicacion_app/`, con permisos, preview, grabación, review, upload, submit y polling básico.

4. **Fase 4 — Evaluación mínima y pipeline de job**  
   Se define el bundle consolidado, la creación de `evaluation_id`, los estados del job, transcript, audio features básicas y el placeholder visual que no bloquea el MVP.

5. **Fase 5 — Informe final, renderer y exportables**  
   Se fija `UiCommunicationReportV1`, el assembler, el renderer, la exportación HTML/JSON/PNG y la experiencia final con **reproductor pequeño del vídeo en la parte superior del informe**.

6. **Fase 6 — Endurecimiento, embed final y compatibilidad lógica con Moodle**  
   Se cierra la serialización final del resultado, el contrato lógico de `final_result`, el puente de ACK y la preservación de outputs compatibles con cuaderno/Moodle sin inventar su implementación concreta.

## Orden y dependencias entre fases

```text
Fase 1
  -> Fase 2
     -> Fase 3
        -> Fase 4
           -> Fase 5
              -> Fase 6
```

### Dependencias lógicas
- **Fase 1** debe ir primero porque define surface, router, contexto y bootstrap. Sin eso no existe identidad estable para attempts, recordings ni UI.
- **Fase 2** depende de Fase 1 porque `attempt_id` y `recording_id` deben colgar de una sesión y un contexto válidos.
- **Fase 3** depende de Fase 2 porque la UI necesita endpoints de attempt/upload estables para grabar sin mocks frágiles.
- **Fase 4** depende de Fase 2 y Fase 3 porque la evaluación necesita `recording_id`, artefactos mínimos y un flujo submit/polling definido.
- **Fase 5** depende de Fase 4 porque no conviene fijar el renderer final antes de cerrar el shape del report y del bundle.
- **Fase 6** depende de Fase 5 porque el `final_result` debe serializar un informe ya estable, con HTML, JSON, snapshot y referencia al vídeo.

## Decisiones ya cerradas

1. `comunicacion` no se implementará dentro de `backend/negociacion`.
2. La surface pública de `comunicacion` será distinta de `interfaz_usuario`.
3. La API de `comunicacion` tendrá router y modelos propios.
4. El bundle de evaluación será nuevo y no reutilizará tal cual `FeedbackInputBundleV1`.
5. El report será propio y no reutilizará tal cual `UiFeedbackReportV1`.
6. El MVP reutilizará solo la infraestructura transversal útil: FastAPI, sesiones, TTL/locks, jobs, repositorios simples, patrón embed y tests de contrato.
7. La parte visual avanzada no bloqueará el MVP.
8. El informe final debe mostrar **un reproductor pequeño del vídeo en la parte superior** para que la persona pueda leer la evaluación mientras revisa su propia grabación.

## Decisiones que seguirán abiertas tras este plan

1. Backend definitivo de storage binario para vídeo y poster.
2. Motor exacto de transcript (interno, proveedor externo o pipeline híbrido).
3. Proveedor o algoritmo definitivo de métricas de prosodia.
4. Nivel final de análisis visual/gesticulación.
5. Mecanismo exacto con el que Moodle/cuaderno persistirá `video_ref` o equivalente.
6. Si más adelante conviene extraer utilidades compartidas entre `interfaz_usuario_app` y `comunicacion_app`.

## Definición clara del MVP

El MVP que este plan deja preparado es:
- bootstrap de sesión de `comunicacion`,
- creación de `attempt_id`,
- registro de `recording_id` con `video_ref` y poster opcional,
- submit para evaluación,
- job mínimo que produzca transcript + audio features básicas + visual placeholder compatible,
- assembler de `UiCommunicationReportV1`,
- renderer final del informe con vídeo pequeño arriba,
- exportables `summary_html`, `payload_json` y snapshot,
- y emisión lógica de `final_result` compatible con un patrón tipo Moodle/cuaderno.

## Qué partes quedan fuera del MVP

- scoring visual fino y heurísticas cerradas de gesticulación,
- chunked upload,
- editor de vídeo en frontend,
- comparativa entre múltiples attempts,
- storage binario distribuido definitivo,
- integración real con el repo de Moodle,
- versionado multi-tenant o persistencia histórica avanzada.

## Cómo se conectará lógicamente con Moodle más adelante

La integración con Moodle **no debe inventarse ahora** porque en esta tarea no tenemos acceso a ese repo. Aun así, sí conviene diseñar correctamente las salidas que nuestra app debe producir.

### Qué salidas de la actividad deberán existir sí o sí
1. `payload_json` serializable del informe final.
2. `summary_html` o HTML equivalente listo para persistencia/render posterior.
3. `report_snapshot_png` o snapshot equivalente del informe.
4. `video_ref` o referencia opaca al vídeo grabado.
5. `evaluation_id`, `attempt_id`, `recording_id` y metadatos de correlación.
6. `payload_hash` o firma estable para ACK y trazabilidad.

### Qué shape de datos final conviene preservar
El flujo debe ser capaz de producir un objeto lógico final que contenga, como mínimo:
- identidad (`session_id`, `evaluation_id`, `activity_id`),
- renderizado (`summary_html`, `report_snapshot_png`),
- datos fuente (`payload_json`),
- media (`video_ref`, `poster_frame_ref`, `duration_ms`),
- y metadatos de integridad (`payload_hash`, `schema_version`, `created_at`).

### Cómo este diseño mantiene compatibilidad con negociación
Se conserva el patrón fuerte ya presente en negociación:
- informe serializable,
- snapshot capturable,
- payload JSON autocontenido,
- emisión final mediante `final_result`,
- ACK correlacionado,
- y separación entre renderer local y persistencia externa.

La diferencia es que `comunicacion` añade un bloque explícito de media para vídeo y poster, sin mezclar semánticas de negociación por turnos.

### Por qué NO hace falta resolver ahora Moodle
Porque el simulador puede construirse correctamente si define con precisión:
- qué produce al final,
- cómo se serializa,
- qué se puede capturar visualmente,
- y qué referencia estable entrega sobre el vídeo.

La fase posterior con acceso al repo de Moodle solo tendrá que decidir **cómo guardar o consumir** esas salidas, no redefinir la arquitectura interna de `comunicacion`.

## Archivos del repo inspeccionados para elaborar el plan

### App, routing y runtime transversal
- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/sessions/state.py`
- `backend/sessions/lifecycle.py`
- `backend/sessions/surface_scope.py`
- `backend/sessions/session_lock.py`

### Evaluación y almacenamiento actuales
- `backend/evaluacion/api/router.py`
- `backend/evaluacion/contracts/models.py`
- `backend/evaluacion/engine/service.py`
- `backend/evaluacion/engine/assembler.py`
- `backend/evaluacion/engine/flow_config.py`
- `backend/evaluacion/storage/models.py`
- `backend/evaluacion/storage/in_memory_repository.py`

### Frontend y contrato embed existentes
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/tests/test_public_interfaz_usuario_serving.py`
- `backend/tests/test_embed_final_result_contract.py`

### Documentación previa releída
- `docs/comunicacion/README.md`
- `docs/comunicacion/bloque-a-arquitectura.md`
- `docs/comunicacion/bloque-b-pipeline-y-estado.md`
- `docs/comunicacion/bloque-c-ui-y-embed.md`
- `docs/comunicacion/bloque-d-informe-y-feedback.md`
- `docs/comunicacion/implementacion/README.md`
- `docs/comunicacion/implementacion/01-backend-y-rutas.md`
- `docs/comunicacion/implementacion/02-pipeline-recording-y-artefactos.md`
- `docs/comunicacion/implementacion/03-ui-captura-api-y-estados.md`
- `docs/comunicacion/implementacion/04-evaluacion-y-report.md`
- `docs/comunicacion/implementacion/05-cambios-transversales-y-riesgos.md`

## Índice de fases

- [fase-1.md](./fase-1.md)
- [fase-2.md](./fase-2.md)
- [fase-3.md](./fase-3.md)
- [fase-4.md](./fase-4.md)
- [fase-5.md](./fase-5.md)
- [fase-6.md](./fase-6.md)

## Recomendación final

La forma más segura de implementar `comunicacion` en este repo es **cerrar primero los contratos y cortes verticales mínimos**, no perseguir una arquitectura universal desde el primer día. Este plan ordena el trabajo para llegar rápido a un MVP útil, manteniendo compatibilidad lógica con el patrón actual de negociación y dejando la integración real con Moodle para cuando ese repositorio pueda inspeccionarse.
