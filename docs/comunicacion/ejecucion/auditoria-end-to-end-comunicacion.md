# Auditoría end-to-end de `comunicacion`

## 1. Objetivo de la auditoría

Auditar de arriba abajo el flujo `comunicacion` ya implementado en este repositorio para determinar:

1. qué partes funcionan realmente
2. qué capas están correctamente conectadas entre sí
3. qué contratos se cumplen de forma efectiva
4. qué artefactos se preservan de punta a punta
5. qué fallos o desacoples reales existen
6. qué riesgos quedan antes de una integración futura con Moodle/cuaderno

La auditoría se ha centrado en el sistema del simulador. No ha intentado implementar Moodle, persistencia LMS real ni nuevas features grandes.

## 2. Alcance revisado

Se revisaron estas capas:

- **Arquitectura y routing** (`/comunicacion`, `/api/comunicacion`, surface, contextos, binding)
- **Sesión y bootstrap**
- **Attempt y recording**
- **App pública de captura**
- **Evaluación mínima**
- **Informe final**
- **`final_result`, bridge embed y ACK**
- **Regresión mínima respecto a `interfaz_usuario` / patrón embed existente**

## 3. Mapa real del flujo end-to-end

El flujo efectivo implementado y validado es:

```text
/comunicacion
  -> POST /api/comunicacion/sessions/bootstrap
  -> POST /api/comunicacion/attempts
  -> POST /api/comunicacion/attempts/{attempt_id}/upload
  -> POST /api/comunicacion/attempts/{attempt_id}/submit
  -> GET /api/comunicacion/evaluations/{evaluation_id}
  -> GET /api/comunicacion/evaluations/{evaluation_id}/report
  -> export JSON / HTML / PNG desde frontend
  -> emit final_result_available
  -> emit final_result
  -> aceptar ACK final_result_saved correlacionado
```

### Artefactos que pasan entre capas

- **bootstrap**: `user_id`, `session_id`, `context_id`, `public_slug`, `capture_policy`
- **attempt**: `attempt_id`, `status`
- **upload**: `recording_id`, `video_ref`, `poster_frame_ref`
- **submit/status**: `evaluation_id`, `status`, `stage`, `report_available`
- **report**: `UiCommunicationReportV1` con `media`, `video_panel`, `exports`, `provenance`
- **final_result**: `summary_html`, `snapshot_png_dataurl`, `payloadjson`, `video_ref`, `poster_frame_ref`, `duration_ms`, `session_id`, `attempt_id`, `recording_id`, `evaluation_id`, `payload_hash`

## 4. Componentes backend implicados

### Routing y surface
- `backend/api/app.py`
- `backend/comunicacion/api/router.py`
- `backend/sessions/surface_scope.py`

### Contexto y sesión
- `backend/comunicacion/contexts/resolver.py`
- `backend/comunicacion/contexts/public_mapping.py`
- `backend/comunicacion/contexts/session_binding.py`
- `backend/comunicacion/services/session_service.py`

### Attempt / recording
- `backend/comunicacion/services/attempt_service.py`
- `backend/comunicacion/services/recording_service.py`
- `backend/comunicacion/storage/models.py`
- `backend/comunicacion/storage/repository.py`

### Evaluación y report
- `backend/comunicacion/services/evaluation_service.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/evaluacion/engine/communication_bundle_builder.py`
- `backend/evaluacion/engine/communication_evaluators.py`
- `backend/evaluacion/engine/communication_report_assembler.py`
- `backend/evaluacion/contracts/communication_models.py`

### Final result / embed
- `backend/comunicacion/final_result_models.py`
- `backend/comunicacion_app/app.js`

## 5. Componentes frontend implicados

- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/report_view.js`
- `backend/comunicacion_app/styles.css`

## 6. Fases verificadas

Se verificó la conexión real entre las fases documentadas:

- **Fase 1**: surface, router, bootstrap y contextos propios
- **Fase 2**: attempt, recording y refs ligeras en sesión
- **Fase 3**: shell pública de captura y máquina de estados
- **Fase 4**: submit, evaluación mínima, estados/stages y report JSON
- **Fase 5**: informe final, renderer, vídeo pequeño y exportables
- **Fase 6**: `final_result`, `final_result_available`, bridge embed y ACK

## 7. Tests ejecutados

### Bloque sesión/contexto
- `python -m pytest backend/tests/test_comunicacion_bootstrap_api.py backend/tests/test_comunicacion_context_binding.py backend/tests/test_comunicacion_session_refs.py -q`

### Bloque attempt/recording
- `python -m pytest backend/tests/test_comunicacion_attempt_repository.py backend/tests/test_comunicacion_recording_repository.py backend/tests/test_comunicacion_attempt_api.py -q`

### Bloque serving/app pública
- `python -m pytest backend/tests/test_public_comunicacion_serving.py backend/tests/test_public_comunicacion_app_assets.py -q`

### Bloque evaluación mínima
- `python -m pytest backend/tests/test_communication_bundle_builder.py backend/tests/test_communication_evaluation_job.py backend/tests/test_communication_status_api.py backend/tests/test_communication_visual_placeholder.py -q`

### Bloque report/final-result/embed
- `python -m pytest backend/tests/test_communication_report_contract.py backend/tests/test_communication_report_api.py backend/tests/test_communication_report_renderer.py backend/tests/test_communication_report_export_contract.py backend/tests/test_communication_final_result_contract.py backend/tests/test_communication_report_exports_integrity.py backend/tests/test_comunicacion_embed_final_result_contract.py -q`

### Regresión mínima fuera de `comunicacion`
- `python -m pytest backend/tests/test_public_interfaz_usuario_serving.py backend/tests/test_embed_final_result_contract.py backend/tests/test_phase8_second_official_context.py -q`

### Smoke test HTTP encadenado
- bootstrap → attempt → upload → submit → status → report con `fastapi.testclient.TestClient` en un script ad hoc de auditoría

## 8. Resultados por capa

### A. Arquitectura

**Veredicto:** bien resuelta y razonablemente aislada.

#### Lo que funciona bien
- `comunicacion` tiene **router propio** (`/api/comunicacion`) y **surface pública propia** (`/comunicacion`).
- El aislamiento respecto a `negociacion` es real a nivel de namespace, contratos, renderer y servicio de evaluación.
- El único cambio transversal relevante sigue siendo pequeño y razonable: ampliar `SessionSurface` para admitir `'comunicacion'`.

#### Acoples reales detectados
- No se detectó acoplamiento funcional con `backend/negociacion/*` dentro del flujo `comunicacion`.
- Sí existe reutilización legítima de infraestructura transversal: FastAPI, sesiones, TTL y patrón embed.

#### Conclusión de capa
A nivel arquitectónico, `comunicacion` está suficientemente desacoplado para seguir evolucionando sin contaminar `negociacion`.

### B. Sesión y contexto

**Veredicto:** sólido y ligero.

#### Lo que funciona bien
- Bootstrap funciona tanto creando identidad nueva como rehidratando una sesión existente.
- El binding de surface protege frente a conflictos de surface.
- El binding de contexto protege frente a conflictos de `context_id`.
- `communication_runtime` guarda solo refs ligeras:
  - `active_attempt_id`
  - `last_recording_id`
  - `latest_evaluation_id`
  - `capture_status`

#### Hallazgos
- No se observó almacenamiento de blobs, HTML grandes, PNG, report completo ni payloads pesados dentro de sesión.
- El estado de sesión no parece inflarse indebidamente en el flujo auditado.

#### Riesgo residual
- Si en el futuro se decidiera cachear report completo o snapshots dentro de sesión, habría riesgo de inflación; hoy no ocurre.

### C. Attempt y recording

**Veredicto:** correctamente conectado para el MVP.

#### Lo que funciona bien
- `create_attempt` exige sesión existente y surface correcta.
- `get_attempt` valida ownership por `user_id` + `session_id`.
- `attach_recording_to_attempt` valida ownership, estado del attempt y metadata mínima (`mime_type`, `duration_ms`, `video_ref`).
- El `attempt` pasa de `draft` a `uploaded` y la sesión registra refs ligeras coherentes.

#### Hallazgos
- `video_ref` es conscientemente provisional (`client-temp://...`) y esa provisionalidad está bien marcada en código y documentación.
- No hay storage binario real, pero el contrato no lo finge: preserva una referencia opaca/provisional coherente para el simulador.

#### Riesgo residual
- No existe persistencia duradera de vídeo ni verificación de que `video_ref` apunte a un asset realmente accesible fuera del navegador que originó la captura.

### D. App pública de captura

**Veredicto:** la máquina de estados del MVP está bien resuelta; el flujo base encadena correctamente.

#### Flujo validado
```text
intro -> permissions -> preview -> recording -> review -> uploading
review -> submit -> processing -> report
```

#### Lo que funciona bien
- La shell pública está separada del frontend de `interfaz_usuario`.
- Los estados principales existen y tienen transiciones explícitas.
- `MediaRecorder`, preview en vivo y review del blob local están diferenciados en estado y UI.
- El upload registra metadata y vuelve a `review`, permitiendo separar grabación local de envío a evaluación.

#### Hallazgos
- No se detectaron estados muertos obvios en la máquina de estados principal.
- `processing` y `report` están realmente conectados a submit/poll/report, no son placeholders puramente visuales.

#### Limitaciones reales
- La parte de permisos y grabación está validada por tests de contrato y smoke, no por automatización real de navegador con cámara/micro.
- Por tanto, la integración con APIs del navegador está razonablemente estructurada, pero no totalmente certificada contra navegadores reales desde esta auditoría CLI.

### E. Evaluación mínima

**Veredicto:** el circuito backend está cerrado y honesto para un MVP placeholder.

#### Lo que funciona bien
- `submit` crea `evaluation_id` real.
- El job mantiene estados útiles: `queued`, `running`, `completed`, `failed`.
- Los stages son coherentes con el pipeline declarado.
- `bundle_builder` conecta attempt + recording + contexto en un bundle válido.
- Los placeholders de transcript, audio y visual están explícitamente marcados como tales.

#### Hallazgos
- El pipeline es honesto: no se presenta transcript real ni análisis acústico/visual real cuando todavía no existen.
- El circuito `review -> submit -> processing -> report` funciona de verdad en la verificación HTTP encadenada y en la suite de tests.

#### Limitación observada
- En el smoke test HTTP la evaluación completó tan rápido que solo se observó el estado final `completed`. Eso no rompe el circuito, pero muestra que el executor en proceso puede hacer que el polling vea pocos stages intermedios en entornos rápidos.

### F. Informe final

**Veredicto:** estable y útil dentro del simulador.

#### Lo que funciona bien
- El assembler produce `UiCommunicationReportV1` con shape estable.
- El report incluye `header`, `media`, `video_panel`, `block_cards`, `timeline`, `recommendations`, `provenance`, `exports` y `placeholders`.
- El vídeo pequeño superior está realmente integrado en el renderer y aporta valor práctico: permite contrastar la lectura con la grabación.
- Los exportables HTML, JSON y PNG son coherentes entre sí y con el report final.

#### Hallazgos
- El report final preserva `video_ref`, `poster_frame_ref`, `duration_ms`, `recording_id` y los exportables que luego reutiliza Fase 6.
- `report_view.js` reusa el mismo report para render, serialización HTML y captura PNG simplificada.

#### Limitaciones reales
- El snapshot PNG del backend assembler sigue siendo placeholder estático; la captura útil/final del informe la resuelve el cliente con canvas en `report_view.js`.
- Eso es coherente con la arquitectura actual, pero conviene recordarlo antes de conectar un LMS que quiera snapshots definitivos del DOM.

### G. `final_result`, embed y ACK

**Veredicto:** casi cerrado; durante la auditoría se detectó y corrigió un desacople real menor.

#### Lo que ya funcionaba bien
- `buildCommunicationFinalResultPayload(...)` produce un payload autocontenido con los artefactos exigidos.
- El envelope `final_result` incluye `ns`, `v`, `type`, `correlation_id`, `session_id`, `context_id` y `public_slug`.
- El bridge distingue correctamente comportamiento standalone vs embed.
- El ACK exige correlación por `session_id` + `activityid` + al menos una coincidencia fuerte (`evaluation_id`, `payload_hash` o `correlation_id`).
- El filtrado por `parent_origin` funciona.

#### Fallo real detectado en auditoría
- `comunicacion` emitía `final_result`, pero **no emitía `final_result_available`** como sí hace el patrón embed ya asentado en `interfaz_usuario`.
- Esto no rompía la entrega principal del `final_result`, pero dejaba el contrato menos alineado con el bridge existente y hacía la capa G menos homogénea para una integración LMS futura.

#### Fix mínimo aplicado
- Se añadió la emisión previa de `final_result_available` en modo embed, con payload ligero de disponibilidad (`evaluation_id`, `activity_type`, `title`, `available_exports`, `score_global_100`, `stars_0_5`, `recording_id`).
- Se añadió verificación específica en tests para asegurar la secuencia:

```text
final_result_available -> final_result
```

#### Resultado tras el fix
La capa G queda contractualmente más alineada con el patrón embed existente del repositorio y mejor preparada para un LMS futuro, sin implementar Moodle real.

#### Cierre contractual posterior (alineación Moodle)
Tras esta auditoría se endureció el contrato operativo del bridge `comunicacion`:

- `final_result_available` se mantiene como evento de disponibilidad y se emite antes de `final_result`.
- El ACK `final_result_saved` ahora requiere de forma obligatoria match de `payload_hash` además de `session_id` y `activityid`.
- `evaluation_id` y `correlation_id` quedan como correladores complementarios de trazabilidad.
- En embed real (`embed=1` + runtime embebido), `parent_origin` debe venir explícito; si falta, el flujo marca `embed_parent_origin_missing` y no emite al parent.

## 9. Lista de fallos reales detectados

1. **Falta de emisión de `final_result_available` en `comunicacion`**.
   - Impacto: desacople menor respecto al patrón embed ya asentado en `interfaz_usuario`.
   - Severidad: media-baja.
   - Estado: corregido en esta auditoría.

No se detectaron otros fallos funcionales reproducibles en la conexión entre capas dentro del alcance del simulador.

## 10. Fixes aplicados

### Fix 1 — Emisión de `final_result_available`
Se añadió emisión explícita de `final_result_available` antes de `final_result` en `backend/comunicacion_app/app.js`, solo en flujo embed.

### Fix 2 — Cobertura de tests del contrato embed
Se ajustó `backend/tests/test_comunicacion_embed_final_result_contract.py` para verificar que la secuencia emitida sea:
- `final_result_available`
- `final_result`

### Fix 3 — Smoke público del asset
Se ajustó `backend/tests/test_public_comunicacion_serving.py` para dejar explícito que el asset público expone el nuevo helper de disponibilidad del bridge final.

## 11. Lista de riesgos pendientes

1. **Storage de media todavía provisional**: `video_ref` sigue siendo opaco/provisional y no garantiza persistencia real fuera del navegador/origen de captura.
2. **Executor en proceso**: suficiente para simulador/MVP, no para cargas reales o media pesada.
3. **Captura PNG final en cliente**: útil y coherente, pero no pixel-perfect ni persistida por backend.
4. **Placeholders de evaluación**: transcript, audio y visual son honestos, pero siguen siendo provisionales hasta integrar extracción real.
5. **ACK no persistido en backend**: hoy la confirmación vive en estado frontend embebido.
6. **Integración LMS todavía fuera de repo**: falta definir cómo el contenedor externo persistirá/consumirá `video_ref`, snapshots, HTML y ACKs.

## 12. Veredicto final

### Qué funciona bien
- arquitectura aislada respecto a `negociacion`
- bootstrap/contexto/surface
- refs ligeras en sesión
- create attempt / upload recording / ownership
- máquina de estados principal de captura
- submit / evaluación mínima / report
- informe final con vídeo superior y exportables
- `final_result` autocontenido y ACK correlacionado

### Qué funciona de forma provisional
- transcript placeholder
- audio features placeholder
- visual placeholder
- `video_ref` provisional
- snapshot PNG simplificado/canvas
- ejecución del job en proceso

### Qué no está listo
- storage binario definitivo
- analítica audiovisual real
- persistencia externa de artefactos
- integración Moodle/cuaderno real

### ¿Puede darse por cerrado dentro del simulador?
**Sí, con una matización importante:** dentro del alcance del simulador, el sistema `comunicacion` puede darse por **cerrado y coherente** tras esta auditoría y el fix mínimo aplicado al bridge embed. No está listo para resolver Moodle real, pero sí está listo como flujo completo del simulador y como base contractual razonable para una integración futura.
