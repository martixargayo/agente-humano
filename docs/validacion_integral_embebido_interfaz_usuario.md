# Validación integral embebido — `interfaz_usuario`

Fecha de ejecución: 2026-03-20 UTC.

## 1. Piezas auditadas

Se auditó y/o ejecutó validación sobre estas zonas implicadas en el frontend público embebible:

- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/feedback_report_view.js`
- `backend/evaluacion/contracts/models.py`
- `backend/negociacion/optimizador/session_bridge.py`
- `backend/tests/*`

## 2. Auditoría previa ultra concreta

### 2.1 Qué piezas del flujo embebido existen realmente

Tras inspección de código y tests, el sistema sí contiene:

- bootstrap real de sesión vía `/api/interfaz_usuario/sessions/bootstrap`
- identidad consolidada (`user_id`, `session_id`, `conversation_id`, `context_id`, `public_slug`)
- diferenciación de bootstrap `new` vs `rehydrated`
- `embed mode` explícito por query param y fallback por iframe
- mensajes al padre:
  - `ready`
  - `height`
  - `error`
  - `final_result_available`
  - `final_result`
- parseo explícito de `423 session_busy` con `Retry-After`
- pipeline final de evaluación y reporte
- exportación/serialización del informe a:
  - HTML
  - JSON
  - PNG
- botones visibles de exportación en la pantalla final

### 2.2 Qué piezas son críticas para pruebas de navegador real

Estas requieren navegador real para validación visual completa:

- layout embebido vs standalone
- emisión efectiva de `postMessage` hacia `window.parent`
- sincronización real de `ready` / `height`
- captura PNG renderizada con `foreignObject` + `canvas`
- interacción real con botones de descarga y comportamiento visual posterior

### 2.3 Qué cobertura automática existía ya

Existía cobertura útil en backend para:

- rutas públicas y serving
- binding de contexto y bootstrap
- runtime/session locks
- evaluación HTTP end-to-end
- session lifecycle
- contexto alternativo oficial

Faltaba o era débil en:

- contrato actualizado del bootstrap (`session_bootstrap_state`, `existing_session`)
- asset contract del payload final con `summary_html` / `payloadjson`
- evidencia integral consolidada en un único documento

### 2.4 Fragilidades detectadas antes de corregir

Hallazgos de auditoría:

1. `FeedbackReportView.renderReport()` añadía listeners globales de `document.click` en cada render; esto era especialmente frágil al serializar/exportar el informe múltiples veces.
2. El payload final emitido al padre usaba `report_html` / `report_json`, pero no exponía aliases explícitos `summary_html` / `payloadjson`, que son los nombres más esperables para persistencia/consumo externo.
3. Había tests backend contractuales desalineados con el shape actual del bootstrap.
4. La suite completa tenía además 5 fallos reales ajenos al camino embebido puro pero sí relevantes para la confianza global del repo; se corrigieron en esta ronda para dejar la suite en verde.

## 3. Pruebas ejecutadas realmente

### 3.1 Checks sintácticos y compilación

- `python -m py_compile backend/interfaz_usuario/__init__.py backend/interfaz_usuario/models.py backend/interfaz_usuario/services.py backend/api/app.py backend/evaluacion/contracts/models.py backend/negociacion/optimizador/session_bridge.py`
- `node --check backend/interfaz_usuario_app/app.js`
- `node --check backend/interfaz_usuario_app/feedback_report_view.js`

### 3.2 Batería focalizada embebido/runtime/evaluación

- `pytest -q backend/tests/test_phase3_context_session_binding.py backend/tests/test_phase4_public_context_surface.py backend/tests/test_phase4_phase5_session_runtime.py backend/tests/test_phase6_evaluation_context_aware.py backend/tests/test_phase8_second_official_context_e2e_http.py backend/tests/test_public_interfaz_usuario_serving.py`

### 3.3 Batería amplia de regresión

- `pytest -q backend/tests`

## 4. Hallazgos reales y ajustes realizados

### 4.1 Ajustes funcionales pequeños

1. **Payload final enriquecido para persistencia/consumo externo**
   - Se añadieron `summary_html` y `payloadjson` como aliases explícitos del payload final emitido en `final_result`.

2. **Corrección de fuga de listeners en render/export**
   - Se evitó acumular listeners globales redundantes al rerenderizar o serializar el informe fuera de la pantalla viva.

3. **Corrección menor transversal detectada por la suite completa**
   - Se corrigió un `NameError` real en `backend/negociacion/optimizador/session_bridge.py` por falta de import de `get_session_store`.

### 4.2 Ajustes de tests

Se actualizaron tests contractuales que estaban asumiendo comportamientos ya superados por la implementación actual:

- shape y semántica del bootstrap en `test_phase3_context_session_binding.py`
- expectativa E2E HTTP de bootstrap `new` / `rehydrated`
- asset contract de `summary_html` / `payloadjson`
- tests del optimizador que estaban creando sesiones bajo la surface equivocada
- expectativas de contexto alternativo que dependían de campos no presentes o de texto no alineado con los assets reales

## 5. Estado validado por área

### A. Rutas públicas y serving

**Validado automáticamente**

- `/interfaz_usuario`
- `/interfaz_usuario/`
- `/interfaz_usuario/<slug>`
- `/interfaz_usuario/<slug>/`
- `/interfaz_usuario/app.js`
- `/interfaz_usuario/feedback_report_view.js`
- `/interfaz_usuario/avatar_runtime/bootstrap.js`

**Garantía actual**

- responden 200
- las referencias a assets públicos son absolutas y correctas
- no se reintrodujeron rutas relativas antiguas tipo `./app.js`

### B. Bootstrap de sesión real

**Validado automáticamente**

- bootstrap con identidad real
- `session_id` disponible
- `conversation_id` y `previous_response_id` preservados cuando existen
- `session_bootstrap_state = new` en primera materialización
- `session_bootstrap_state = rehydrated` en reapertura/reuso real
- `existing_session` coherente

**Garantía actual**

- standalone y flujo HTTP público no rompen la consolidación de identidad
- la rehidratación básica quedó demostrada en tests HTTP y unitarios

### C. Embed mode

**Validado automáticamente de forma contractual**

- existencia de `readEmbedModeFromUrl()`
- existencia de `bootstrapPayload()`
- serving correcto del `index.html` con CSS/JS de embebido

**No validado completamente de forma visual automática**

- activación real de `data-embed-mode` en DOM dentro de iframe
- comportamiento visual exacto standalone vs embed

### D. `ready`

**Validado contractualmente**

- la implementación existe en `app.js`
- depende de identidad consolidada y `scenarioReady`
- la emisión se deduplica por `embedReadySessionKey`

**No validado completamente en navegador real en este entorno**

- no había navegador/headless instalado y, por instrucción del entorno, no se instaló uno nuevo

### E. `height`

**Validado contractualmente**

- existe medición de superficies visibles
- existe agenda de emisión ligada a cambios de vista/render/focus/pageshow/resize/visibility

**No validado completamente en navegador real**

- no se pudo observar el `postMessage` real ni medir el `height_px` en un padre real por falta de browser runtime

### F. `error` y `session_busy`

**Validado automáticamente**

- backend responde `423`
- incluye `error = session_busy`
- incluye `Retry-After`
- el runtime/session tests cubren el lock distribuido
- el frontend tiene parseo tipado (`ApiError`) y contractualmente expone la semántica correcta

**Garantía actual**

- la semántica backend de `session_busy` está probada
- el frontend tiene soporte explícito para consumirla y notificar al padre

### G. Informe final visible

**Validado automáticamente a nivel de pipeline**

- creación de evaluación
- polling HTTP de estado
- obtención de `ui_feedback_report.v1`
- coherencia de `header`, `block_cards`, `trajectory_chart` y `provenance`

**No validado visualmente al 100%**

- render final en navegador real no pudo inspeccionarse visualmente en este entorno

### H. `summary_html`

**Validado automáticamente a nivel contractual**

- ahora existe explícitamente en el payload final del frontend
- se construye a partir de la serialización HTML del informe

**Límite**

- no se ejecutó una prueba de navegador real que materialice el HTML descargado y lo compare pixel a pixel con la vista viva

### I. `payloadjson`

**Validado automáticamente a nivel contractual y de reporte**

- existe explícitamente en el payload final
- el reporte HTTP E2E devuelve `ui_feedback_report.v1` con estructura útil y no vacía
- incluye correlación/provenance (`context_id`, `flow_id`) cuando corresponde

### J. PNG / captura visual

**Validado técnicamente hasta donde permitió el entorno**

- existe helper real `captureReportAsPng`
- la estrategia no es mock: usa `foreignObject`, `Image`, `canvas` y `toBlob`
- la pantalla final expone botón visible de descarga PNG

**No validado visualmente de extremo a extremo**

- no había navegador/headless disponible
- no se generó artefacto PNG real en este entorno

### K. Botones de exportación

**Validado automáticamente**

- existen botones visibles para:
  - HTML
  - JSON
  - PNG
  - volver
- están conectados en `app.js`

### L. `final_result_available` y `final_result`

**Validado contractualmente**

- ambos mensajes existen en el frontend
- `final_result` se emite tras `fetchEvaluationReport()`
- `final_result_available` se emite cuando el reporte queda listo y también cuando el usuario descarga
- el payload final incluye reporte, HTML serializado y JSON serializable

### M. Descargas iniciadas por usuario / eventos al padre

**Validado contractualmente**

- tras descargar HTML/JSON/PNG se emite `final_result_available` con `exported_format`
- la capa común de mensajería usa `targetOrigin` explícito
- no se usan `postMessage("*")`

### N. Reapertura / reentrada razonable

**Validado automáticamente de forma parcial**

- bootstrap rehidratado
- continuidad de sesión/contexto
- no regresión obvia en serving al reabrir rutas públicas

**No validado completamente en navegador real**

- no se pudo observar secuencia completa de reentrada con iframe padre real

## 6. Qué sí puedo afirmar ahora con confianza

1. El **backend HTTP público** del simulador para `interfaz_usuario` está consistente y cubierto por tests.
2. El **bootstrap real** de sesión y su distinción `new` / `rehydrated` están validados.
3. El **pipeline de evaluación** produce un `ui_feedback_report.v1` coherente y no vacío.
4. El frontend público expone de forma consistente:
   - export HTML
   - export JSON
   - export PNG
   - botones visibles de descarga
   - mensajes `final_result_available` y `final_result`
5. La semántica de **`session_busy` + `Retry-After`** está validada de forma real en backend y soportada explícitamente en frontend.
6. La **suite completa de `backend/tests` quedó en verde** al cerrar este turno.

## 7. Qué no puedo garantizar al 100% en este entorno

Por limitación objetiva del entorno:

- no había navegador/headless instalado
- no se usó instalación ad hoc de browser por restricción operativa del turno

Por tanto, **no puedo afirmar con evidencia de ejecución visual directa**:

- el layout exacto standalone vs embed en un DOM real
- la observación real de `postMessage` en un padre vivo
- la captura PNG final renderizada visualmente
- la ausencia total de glitches visuales en todos los navegadores

## 8. Pruebas manuales reproducibles exigentes recomendadas

Cuando haya un navegador disponible, ejecutar esta batería:

1. **Standalone**
   - abrir `/interfaz_usuario`
   - confirmar `document.documentElement.dataset.embedMode === "0"`
   - completar bootstrap

2. **Embed forzado**
   - cargar `/interfaz_usuario/negociacion-validacion?embed=1` dentro de un iframe en una página padre que escuche `message`
   - confirmar `data-embed-mode="1"`
   - capturar mensajes `ready`, `height`, `final_result_available`, `final_result`, `error`

3. **Iframe fallback**
   - cargar sin `?embed=1` pero dentro de iframe
   - verificar activación automática de modo embebido

4. **Desactivar embebido**
   - abrir dentro de iframe con `?embed=0`
   - confirmar que no se comporta como embed explícito

5. **Session busy**
   - lanzar dos acciones concurrentes contra la misma sesión
   - comprobar bloqueo visual, texto de retry, y mensaje `error` al padre con semántica `session_busy`

6. **Informe final**
   - completar evaluación
   - descargar HTML / JSON / PNG
   - abrir el HTML descargado
   - validar que JSON no está vacío y conserva estructura
   - abrir PNG y comprobar que no está vacío ni truncado

## 9. Conclusión

La validación integral de este turno deja una base mucho más sólida y demostrable para el frontend público embebible:

- el backend y los contratos públicos están consistentes,
- el pipeline final de reporte está disponible y probado hasta el límite razonable del entorno,
- y la suite completa relevante quedó en verde.

El único límite importante que permanece es **la falta de navegador real en este entorno**, lo que impide cerrar con evidencia visual directa la parte de `postMessage` observado en padre, layout embebido exacto y PNG inspeccionado visualmente. Aun así, la validación técnica y contractual ejecutada aquí deja el sistema en un estado objetivamente más confiable que antes de este turno.
