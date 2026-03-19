# Auditoría del frontend real de `interfaz_usuario` frente a multicontexto

## 1. Resumen ejecutivo

### Veredicto corto

**La interfaz pública real no está operativa ahora mismo ni en `/interfaz_usuario` ni en `/interfaz_usuario/{public_slug}`.**

La causa principal **no es un fallo del motor de negociación** ni del bootstrap contextual en sí, sino una **rotura de serving/wiring frontend-backend en la superficie pública**:

1. `index.html` carga `./app.js` y `./feedback_report_view.js` como rutas relativas.  
2. `backend/api/app.py` registra antes una ruta dinámica `/interfaz_usuario/{public_slug}`.  
3. Como resultado, peticiones de assets como `/interfaz_usuario/app.js` y `/interfaz_usuario/feedback_report_view.js` quedan capturadas por la ruta de slug y terminan fallando.  
4. Si `app.js` no carga, **no se ejecuta ningún listener**, no se hace el bootstrap automático, no se registran handlers del botón “Empezar”, no se inicializa el flujo de micrófono y la UI queda “muerta”.

Además, hay una segunda rotura específica de la entrada contextual con slash final:

- en `/interfaz_usuario/{public_slug}/`, las rutas relativas `./app.js` y `./avatar_runtime/bootstrap.js` se resuelven dentro del subdirectorio del slug, lo que lleva a 404 para esos assets.

### Diagnóstico principal

El problema observado de que:

- “Empezar” no funciona,
- el micrófono no conecta,
- la UI por slug no reacciona,

**cuadra completamente con una rotura mixta de frontend + serving HTTP**, no con una adaptación incompleta del `public_slug` dentro de `app.js`.

El soporte multicontexto en el JS está razonablemente conectado; lo que está roto es **la entrega real de los scripts que hacen vivir esa UI**.

---

## 2. Superficie pública encontrada

### URLs reales expuestas

Según `backend/api/app.py`, la app pública de negociación expone:

- `/interfaz_usuario/{public_slug}`
- `/interfaz_usuario/{public_slug}/`
- `Mount("/interfaz_usuario", StaticFiles(..., html=True))`

Es decir, coexisten:

- una entrada baseline servida por el `StaticFiles` mount,
- y dos entradas contextuales que devuelven manualmente `index.html`.

### Qué HTML/JS carga cada una

Todas estas entradas sirven el mismo `backend/interfaz_usuario_app/index.html`.

Ese HTML intenta cargar:

- `./feedback_report_view.js`
- `./avatar_runtime/bootstrap.js`
- `./app.js`

### Diferencias reales entre baseline y slug

**Sí hay diferencia de arranque real, aunque el HTML sea el mismo**, porque la resolución de rutas relativas cambia según la URL base:

- En `/interfaz_usuario/`:
  - `./app.js -> /interfaz_usuario/app.js`
- En `/interfaz_usuario/negociacion-validacion`:
  - `./app.js -> /interfaz_usuario/app.js`
- En `/interfaz_usuario/negociacion-validacion/`:
  - `./app.js -> /interfaz_usuario/negociacion-validacion/app.js`
  - `./avatar_runtime/bootstrap.js -> /interfaz_usuario/negociacion-validacion/avatar_runtime/bootstrap.js`

Esto hace que **la entrada contextual con slash final no sea equivalente a la baseline**, aunque sirva el mismo HTML.

---

## 3. Flujo real esperado de arranque

La secuencia esperada, leyendo `index.html` + `app.js`, es:

1. Se entrega `index.html`.
2. El navegador carga `feedback_report_view.js`, `avatar_runtime/bootstrap.js` y `app.js`.
3. `avatar_runtime/bootstrap.js` monta el runtime 3D y acabará disparando `avatar-runtime-ready` o `avatar-runtime-error`.
4. `app.js`:
   - construye el objeto `ui` desde IDs del DOM,
   - registra listeners de botones,
   - hace bootstrap automático de sesión en un IIFE final,
   - detecta `public_slug` desde `window.location.pathname`,
   - envía ese `public_slug` solo al bootstrap,
   - sincroniza estado del overlay de entrada,
   - gestiona permiso/listado de micrófonos,
   - y deja preparado el envío de turnos y el flujo de feedback.
5. Al pulsar “Empezar”:
   - en modo Hablar: valida permiso/micrófono, intenta arrancar captura y resuelve la entrada;
   - en modo Escribir: resuelve la entrada sin micrófono.
6. Tras eso, la UI debe permitir:
   - hablar,
   - escribir,
   - mandar turnos,
   - cambiar de micrófono,
   - y lanzar feedback.

---

## 4. Flujo real observado / reconstruido

### Lo que pude reproducir

No ejecuté un navegador gráfico completo.  
**Sí pude reproducir la superficie HTTP real y la resolución de assets** con `FastAPI TestClient` y con resolución de URLs relativas.

### Lo observado de forma demostrable

#### Caso A: baseline `/interfaz_usuario/`

- `GET /interfaz_usuario/` responde 200.
- Pero el HTML intenta cargar `./app.js`, que resuelve a `/interfaz_usuario/app.js`.
- Esa URL **no sirve el archivo JS**: queda capturada por la ruta `/interfaz_usuario/{public_slug}` y falla.

#### Caso B: slug sin slash `/interfaz_usuario/negociacion-validacion`

- `GET /interfaz_usuario/negociacion-validacion` responde 200.
- Pero `./app.js` vuelve a resolver a `/interfaz_usuario/app.js`.
- Esa URL vuelve a fallar por la misma colisión con la ruta de slug.

#### Caso C: slug con slash `/interfaz_usuario/negociacion-validacion/`

- `GET /interfaz_usuario/negociacion-validacion/` responde 200.
- Pero `./app.js` resuelve a `/interfaz_usuario/negociacion-validacion/app.js`.
- Esa ruta da 404 porque el `StaticFiles` mount la interpreta como un archivo dentro de un subdirectorio inexistente.
- También falla `./avatar_runtime/bootstrap.js` por el mismo motivo.

### Consecuencia directa

Si `app.js` no carga:

- no se ejecuta el IIFE de init,
- no se hace bootstrap automático,
- no se registran listeners,
- no se activa el flujo de micrófono,
- no se conectan los botones,
- y la interfaz queda visualmente presente pero funcionalmente muerta.

Esto explica de forma directa el síntoma descrito por el usuario.

---

## 5. Auditoría de bootstrap frontend

## Entry points reales

### HTML

`backend/interfaz_usuario_app/index.html`.

### JS principal

`backend/interfaz_usuario_app/app.js`.

### Runtime visual

`backend/interfaz_usuario_app/avatar_runtime/bootstrap.js` y `runtime.js`.

## Funciones de arranque relevantes

### `readPublicSlugFromUrl()`

- Lee `window.location.pathname`.
- Hace `replace(/\/+$/, '')`.
- Extrae `public_slug` con regex `^/interfaz_usuario/([^/]+)$`.

**Conclusión:** el parseo del slug está bien planteado y soporta slash final porque lo recorta antes.

### `bootstrapPayload()`

- parte de `ids()` (`user_id`, `session_id`),
- añade `public_slug` solo si existe.

**Conclusión:** el contrato de bootstrap contextual del frontend está alineado con el backend.

### IIFE final `initInterfazUsuarioSession()`

Hace:

1. `_seedDefaultIds()`
2. `syncSessionBoundaryReset()`
3. `POST /api/interfaz_usuario/sessions/bootstrap` con `bootstrapPayload()`
4. `bindRuntimeReadiness()`
5. `startEntryDevicePolling()`
6. `bootstrapEntryDeviceBackground()`
7. `setEntryMode(InputMode.TALK)`
8. `renderEntryState()`

**Conclusión:** el camino de bootstrap existe y está completo a nivel JS.  
**Pero hoy no se ejecuta en runtime real si `app.js` no llega a cargarse.**

---

## 6. Auditoría de listeners y botones

## Qué botones existen realmente

En el DOM existen, entre otros:

- `#bootstrap`
- `#newConv`
- `#startBtn`
- `#modeTalk`
- `#modeWrite`
- `#sendTextBtn`
- `#finishTurnBtn`
- `#finishNegotiationBtn`
- `#audioDeviceTrigger`

## Qué handlers deberían dispararse

### Botón “Empezar”

- Elemento: `#startBtn`
- Handler: `ui.startBtn.addEventListener('click', () => { void handleStartEntry(); });`
- Función: `handleStartEntry()`

### Activación / cambio de micrófono

- Overlay de entrada: `#startBtn` en modo hablar -> `validateTalkModeForEntry()` -> `requestMicPermissionsForEntry()` / `startVoiceCapture()`
- Selector de micrófono: `#audioDeviceTrigger` -> `toggleAudioDevicePopover()`
- Cambio de dispositivo: botones dinámicos -> `handleAudioDeviceChangeRequest()`

### Turno de voz

- Botón: `#finishTurnBtn`
- Handler: `handleFinishTurn()`

## ¿Están realmente conectados?

**En código, sí. En runtime real, no necesariamente.**

La conexión de listeners depende de que `app.js` cargue y se ejecute. Como hoy `app.js` no está siendo servido correctamente en la superficie pública, el resultado práctico es:

- los botones existen en HTML,
- pero sus listeners no llegan a registrarse,
- por eso “no hacen nada”.

## ¿Hay divergencia HTML vs selectores JS?

Hice contraste estático entre IDs usados por `$('...')` y los IDs declarados en `index.html`.

Resultado:

- la única referencia no presente en HTML es `conversationMode`,
- pero está tratada con `?.remove()` y guards, por lo que **no es la causa de la caída**.

**Conclusión:** no encontré una divergencia DOM/selector que explique el problema principal. El problema principal es anterior: el JS no se entrega bien.

---

## 7. Auditoría del flujo de micrófono

## Flujo esperado

1. `handleStartEntry()`
2. `validateTalkModeForEntry()`
3. `requestMicPermissionsForEntry()`
4. `refreshEntryDevices()`
5. si todo va bien, `startVoiceCapture()`
6. luego `handleFinishTurn()` cierra la captura, transcribe y manda turno.

## Dependencias reales del flujo de micrófono

- `navigator.mediaDevices.getUserMedia`
- `navigator.mediaDevices.enumerateDevices`
- estado `entryPermissionStatus`
- `selectedEntryDeviceId`
- `scenarioReady`
- listeners de `app.js`

## Dónde se rompe hoy

**Antes de entrar realmente en la lógica de micrófono**, porque:

- si `app.js` no carga, no existe `handleStartEntry()` en runtime;
- si no existe ese wiring, el botón “Empezar” no ejecuta validación de permisos ni `startVoiceCapture()`;
- y por tanto el síntoma “conectar micrófono no funciona” es consistente con una UI sin JS vivo.

## ¿Hay un problema intrínseco adicional en la lógica del micrófono?

No encontré uno claramente bloqueante a nivel estático comparable al fallo de serving.

Sí hay complejidad y varios estados (`entryPermissionStatus`, `selectedEntryDeviceId`, `scenarioReady`), pero **el bloqueo principal observado está antes**: la app no llega a ejecutar ese código.

---

## 8. Auditoría de compatibilidad con `context_id` / `public_slug`

## Fase 3: binding de contexto en sesión

Desde frontend público:

- el JS no persiste `context_id` localmente,
- pero sí usa `session_id` y reusa la sesión después del bootstrap,
- `new_conversation` manda solo `user_id` + `session_id`, lo que encaja con herencia de contexto en backend.

**Conclusión:** no vi incompatibilidad directa del frontend con la fase 3.

## Fase 4: `public_slug` y bootstrap contextual

Aquí el frontend está **bien adaptado en lógica**, pero la superficie pública está mal servida:

- `readPublicSlugFromUrl()` detecta el slug correctamente,
- `bootstrapPayload()` lo manda solo en bootstrap,
- eso está alineado con lo esperado.

**Problema real:** al entrar por slug, los assets no quedan servidos de forma equivalente.

## Fase 5: trazas context-aware

El frontend usa metadatos de turno principalmente para mostrar:

- `entry_contract.entrypoint`
- `overrides_applied`
- `latest_turn_id`
- `conversation_id_after`
- `trace_count`

No vi dependencia frontend de campos antiguos incompatibles con las trazas context-aware.

## Fase 6: evaluación context-aware

La UI de feedback usa:

- `POST /feedback/evaluations`
- polling de `GET /feedback/evaluations/{id}`
- report en `GET /feedback/evaluations/{id}/report`

El contrato básico encaja.  
Pero `feedback_report_view.js` también está expuesto al mismo problema de serving relativo que `app.js` en baseline/slug sin slash.

## Fase 7: optimizer context-aware

No hay dependencia relevante del frontend público respecto al optimizer. No parece la causa del fallo de la UI pública.

## Fase 8: coexistencia baseline + segundo contexto oficial

La UI no parece asumir hardcodeadamente un único contexto a nivel de payload de bootstrap.

Pero **la entrega de assets sí quedó desalineada al introducir la ruta pública por slug**. Ese es el punto donde la adaptación multicontexto quedó incompleta del lado frontend/surface.

---

## 9. Contratos frontend/backend que cuadran

Estos sí cuadran, leyendo código:

1. `bootstrapPayload()` manda `public_slug` solo en bootstrap.
2. `POST /api/interfaz_usuario/sessions/bootstrap` acepta `public_slug` y `context_id`.
3. `POST /api/interfaz_usuario/negociacion/turn` sigue usando `user_id`, `session_id`, `message`, `new_conversation`.
4. `POST /api/interfaz_usuario/negociacion/new_conversation` encaja con herencia de sesión/contexto.
5. El polling de feedback usa endpoints reales existentes.
6. El parseo de `public_slug` en frontend no contradice el contrato backend.

---

## 10. Contratos frontend/backend que no cuadran

## Contrato roto principal: serving de assets de la app pública

El frontend asume que desde el HTML público puede cargar:

- `./app.js`
- `./feedback_report_view.js`
- `./avatar_runtime/bootstrap.js`

Pero el backend expone una ruta dinámica `/interfaz_usuario/{public_slug}` **antes** del mount estático `/interfaz_usuario`, lo que rompe ese supuesto para ciertos paths.

### Desalineación exacta

- `./app.js -> /interfaz_usuario/app.js`
- backend interpreta `/interfaz_usuario/app.js` como `public_slug="app.js"`
- eso no es un slug válido
- y el asset no se sirve.

## Contrato roto adicional: equivalencia falsa entre slug y slug con slash final

`/interfaz_usuario/{slug}` y `/interfaz_usuario/{slug}/` sirven el mismo HTML, pero **no tienen la misma base URL para resolver assets relativos**.

Eso rompe especialmente:

- `/interfaz_usuario/{slug}/app.js`
- `/interfaz_usuario/{slug}/avatar_runtime/bootstrap.js`
- `/interfaz_usuario/{slug}/feedback_report_view.js`

---

## 11. Hallazgos clasificados por severidad

## H1. BLOQUEANTE — `app.js` no se sirve correctamente en la superficie pública

### Síntoma observable

- Los botones están visibles pero no responden.
- No se registra el bootstrap automático.
- La UI parece “muerta”.

### Causa raíz

Colisión entre:

- `index.html` cargando `./app.js`, y
- la ruta dinámica `/interfaz_usuario/{public_slug}` declarada antes del `StaticFiles` mount.

### Archivos implicados

- `backend/api/app.py`
- `backend/interfaz_usuario_app/index.html`

### Función / línea aproximada

- `backend/api/app.py`: handlers `@app.get("/interfaz_usuario/{public_slug}")` y `@app.get("/interfaz_usuario/{public_slug}/")`
- `backend/interfaz_usuario_app/index.html`: scripts relativos del final del body

### Por qué ocurre

`/interfaz_usuario/app.js` queda capturado como slug en vez de resolverse como archivo estático.

### Impacto real

**Rompe toda la app pública.** Sin `app.js` no hay listeners, bootstrap, ni micrófono.

### Propuesta mínima de corrección

- Evitar que la ruta `{public_slug}` capture rutas de assets.
- Y/o dejar de usar rutas relativas problemáticas para assets críticos del frontend público.
- El fix mínimo correcto debería garantizar que `app.js`, `feedback_report_view.js` y `avatar_runtime/*` se sirvan siempre desde un path estático inequívoco.

---

## H2. BLOQUEANTE — La URL contextual con slash final no es equivalente a la sin slash

### Síntoma observable

- Entrar por `/interfaz_usuario/{public_slug}/` rompe carga de scripts/módulos.

### Causa raíz

Las rutas relativas del HTML se resuelven dentro del subdirectorio del slug cuando la URL termina con `/`.

### Archivos implicados

- `backend/api/app.py`
- `backend/interfaz_usuario_app/index.html`

### Función / línea aproximada

- handler `/interfaz_usuario/{public_slug}/`
- scripts `./app.js`, `./avatar_runtime/bootstrap.js`, `./feedback_report_view.js`

### Por qué ocurre

El navegador resuelve `./app.js` contra `/interfaz_usuario/{slug}/`, dando `/interfaz_usuario/{slug}/app.js`.

### Impacto real

**Rompe la entrada contextual con slash final**, aunque el slug sea válido.

### Propuesta mínima de corrección

- Redirigir siempre a una única forma canónica de URL pública, o
- fijar base/paths absolutos para assets.

---

## H3. ALTO — `feedback_report_view.js` queda roto por el mismo patrón que `app.js`

### Síntoma observable

- El flujo de feedback puede quedar roto incluso aunque el resto de la pantalla cargase parcialmente.

### Causa raíz

La misma colisión de serving de assets para `/interfaz_usuario/feedback_report_view.js`.

### Archivos implicados

- `backend/interfaz_usuario_app/index.html`
- `backend/api/app.py`

### Impacto real

Deja la capa de feedback en estado inconsistente o directamente no disponible.

### Propuesta mínima de corrección

Misma que H1: garantizar serving estático inequívoco de assets JS.

---

## H4. MEDIO — El problema parece de listeners, pero en realidad ocurre antes de registrar listeners

### Síntoma observable

- “Empezar” y el micrófono no hacen nada.

### Causa raíz

No es que `handleStartEntry()` esté mal conectado; es que `app.js` no llega a ejecutarse.

### Archivos implicados

- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/index.html`
- `backend/api/app.py`

### Impacto real

Puede inducir a arreglar el sitio equivocado: listeners/DOM/micrófono, cuando el corte real está en la entrega del JS.

### Propuesta mínima de corrección

Primero arreglar serving/rutas. Solo después reevaluar si queda un bug funcional en listeners o micrófono.

---

## H5. MENOR — `conversationMode` ya no existe en HTML pero permanece referenciado en JS

### Síntoma observable

Referencia residual a `conversationMode`.

### Causa raíz

Código de compatibilidad con una UI anterior.

### Archivos implicados

- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/index.html`

### Impacto real

Bajo: está protegido con optional chaining y guards. No explica la caída actual.

### Propuesta mínima de corrección

Limpiar ese residuo solo después de restaurar operatividad real.

---

## 12. Causa raíz principal o principales

## Causa raíz principal

**La superficie pública quedó mal cerrada al introducir la ruta contextual por slug.**

En concreto:

- se añadió `/interfaz_usuario/{public_slug}` para servir la misma SPA/HTML,
- pero no se aseguró que los assets relativos del frontend siguieran resolviendo correctamente,
- y además la ruta dinámica quedó posicionada de forma que interfiere con archivos estáticos de primer nivel dentro de `/interfaz_usuario`.

## Causa raíz secundaria

**La variante con slash final del slug no es canónica y rompe la resolución de assets relativos.**

---

## 13. Lista priorizada de fixes mínimos

> No se implementan aquí; se listan por prioridad.

### Fix 1 — Restaurar serving inequívoco de assets JS de `interfaz_usuario`

Prioridad máxima.  
Objetivo: que estas rutas funcionen siempre:

- `/interfaz_usuario/app.js`
- `/interfaz_usuario/feedback_report_view.js`
- `/interfaz_usuario/avatar_runtime/bootstrap.js`

### Fix 2 — Canonicalizar la URL contextual pública

Elegir una sola forma canónica para el contexto público:

- o siempre sin slash final,
- o siempre con slash final,

pero garantizando que los assets sigan resolviendo bien.

### Fix 3 — Asegurar que la entrada contextual y baseline compartan exactamente el mismo bootstrap efectivo

Una vez servido el JS, verificar otra vez:

- bootstrap automático,
- botón “Empezar”,
- flujo de micrófono,
- envío de turnos,
- feedback.

### Fix 4 — Solo después, reauditar micrófono y overlay en navegador real

Cuando el JS ya cargue de verdad, entonces sí tiene sentido comprobar si queda un bug secundario de permisos, `scenarioReady` o `startVoiceCapture()`.

---

## 14. Qué NO tocaría todavía

1. **No tocaría prompts ni runtime de negociación.** No son la causa principal de esta rotura.
2. **No tocaría evaluación ni optimizer** salvo para pruebas posteriores; no explican que los botones no respondan.
3. **No refactorizaría `app.js` entero.** La lógica interna no es el primer problema.
4. **No reescribiría el flujo de micrófono** hasta restaurar la carga real de scripts.
5. **No tocaría el parseo de `public_slug` en frontend**: está razonablemente bien.

---

## 15. Veredicto final

### 1. ¿Está el frontend real correctamente adaptado a multicontexto?

**No del todo.**  
La lógica de bootstrap contextual en JS sí está adaptada, pero la **superficie real de serving** no quedó bien cerrada y rompe la operatividad pública.

### 2. ¿Funciona realmente bien `/interfaz_usuario`?

**No.**  
El HTML responde, pero `app.js` y `feedback_report_view.js` no quedan servidos correctamente desde esa entrada.

### 3. ¿Funciona realmente bien `/interfaz_usuario/{public_slug}`?

**No.**  
Sin slash final hereda el mismo problema de `app.js`; con slash final además rompe más assets relativos.

### 4. ¿El problema de botones que no responden cuadra con una adaptación incompleta del frontend?

**Sí**, pero concretamente como **adaptación incompleta de la superficie pública frontend/backend**, no tanto del código de listeners interno.

### 5. ¿El fallo es de frontend puro, de integración frontend/backend, o mixto?

**Mixto**, con centro de gravedad en la integración frontend/backend:

- frontend: usa assets relativos,
- backend: expone rutas dinámicas que interfieren con esos assets.

### 6. ¿Qué arreglaría primero para recuperar operatividad real?

**Primero arreglaría el serving/canonicalización de assets de la interfaz pública.**  
Sin eso, cualquier trabajo sobre botones o micrófono es prematuro.

### 7. ¿Qué partes están bien y no conviene tocar?

- el parseo de `public_slug` en `app.js`,
- el contrato de bootstrap contextual,
- el uso de `session_id`/`new_conversation`,
- y, en general, la lógica de alto nivel del frontend una vez cargado el JS.

## Conclusión final

La evidencia del repo apunta a una explicación muy concreta de por qué “los botones no hacen nada”:

> **el frontend principal no está cargando correctamente en la superficie pública real debido a una colisión de rutas/serving introducida al añadir la entrada contextual por slug.**

Por eso, el siguiente paso correcto no es un refactor del frontend ni del motor, sino un **fix mínimo en la entrega de assets y canonicalización de la URL pública**. Una vez resuelto eso, tendría sentido hacer una segunda pasada para comprobar si queda algún bug menor en el flujo de micrófono o en el overlay de entrada.
