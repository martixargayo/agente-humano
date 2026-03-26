# 01 · Referencia negociación: permisos y entrada (adaptada a comunicación)

## 1) Objetivo del doc
Dejar especificado, con trazabilidad a código real, cómo reemplazar la entrada actual de `comunicacion` por una pantalla única de permisos/configuración de cámara y micrófono inspirada en `interfaz_usuario` (negociación), eliminando por completo:
- la portada tipo “presentación breve grabada”,
- el modo texto/escritura,
- el paso explícito de “Abrir preview”.

## 2) Archivos/pantallas inspeccionados

### Comunicación (estado actual)
- `backend/comunicacion_app/index.html`
- `backend/comunicacion_app/app.js`
- `backend/comunicacion_app/styles.css`

### Negociación / interfaz_usuario (referencia)
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`

## 3) Evidencia exacta encontrada en repo (ids, clases, funciones, handlers, estados)

### 3.1 Comunicación hoy
- Pantalla inicial con header y copy de actividad en `#activityTitle`/`#activitySubtitle`, más `screenIntro` con botón `#startFlowBtn`.
- Flujo actual de entrada dividido en:
  - `screenIntro` → `screenPermissions` → `screenPreview`.
- Permisos usa `#grantPermissionsBtn` y luego `#openPreviewBtn`.
- Selectores de dispositivo actuales: `#videoDeviceSelect`, `#audioDeviceSelect` (`<select>` nativos).
- Estados y transición:
  - constantes `SCREEN_INTRO`, `SCREEN_PERMISSIONS`, `SCREEN_PREVIEW`.
  - `startFlowBtn` mueve a permisos.
  - `grantPermissionsBtn` solicita `getUserMedia`.
  - `openPreviewBtn` abre stream y recién ahí avanza a preview.

### 3.2 Negociación (referencia directa)
- Entrada está centralizada en overlay `#entryOverlay` con card `entry-card` y CTA único `#startBtn`.
- Estado del botón y microcopy se resuelve en `renderEntryState()`.
- En talk-mode se pasa de “Activar micrófono” a “Empezar” según `entryPermissionStatus` + dispositivo válido.
- Listado visual de dispositivos (no `<select>` feo): `entry-device-list`, `entry-device-option`, `entry-device-status`.

### 3.3 Piezas que prueban que hay que eliminar modo texto
- En negociación existen tabs `#entryModeTalk` / `#entryModeWrite`, paneles `#entryTalkContent` / `#entryWriteContent`, y estado `InputMode.WRITE`.
- En `comunicacion` no hay requisito de escritura para este rediseño; por lo tanto se reutiliza la estética/técnica de entrada, **no** el modo write.

## 4) Diagnóstico del estado actual
- UX fragmentada en 3 pantallas antes de grabar.
- Exceso de pasos técnicos visibles (`Conceder permisos`, `Abrir preview`).
- La pantalla de portada aporta poco valor y aumenta fricción.
- Los `<select>` nativos rompen continuidad visual con negociación.

## 5) Referencia visual/técnica exacta (negociación) a usar
- Estructura visual base: overlay + card limpia + CTA principal único + estado contextual.
- Filosofía de interacción: un mismo CTA progresivo según estado del sistema.
- Sistema de dispositivos: listados visuales activos con check, no dropdown básico.
- Estética de blancos: `feedback-screen` y cards en blanco puro en negociación.

## 6) Propuesta detallada de cómo debería quedar

### 6.1 Pantalla única de acceso (nuevo primer paso)
- Sustituir `screenIntro + screenPermissions + screenPreview` por **un solo paso** `screenSetup`.
- Estructura visual inspirada en `entryOverlay`:
  1. título,
  2. texto breve de preparación,
  3. bloque estado cámara/micro (OK/KO),
  4. selector visual de cámara,
  5. selector visual de micrófono,
  6. CTA único progresivo.

### 6.2 Comportamiento del CTA principal
- Si faltan permisos → `Activar cámara y micrófono`.
- Si permisos OK + dispositivos válidos → `Empezar`.
- Al pulsar `Empezar` se pasa al paso intermedio AIDA (doc 02).

### 6.3 Reglas explícitas solicitadas
- Sin modo texto.
- Sin botón “Abrir preview”.
- Sin portada tipo actividad.
- Misma sensación de entrada moderna/limpia de negociación.

## 7) Layout detallado
- Fondo blanco (`#fff` / `#fefefe`) dominante.
- Caja principal blanca con sombra suave y borde bajo contraste.
- Dos sub-bloques de dispositivos:
  - `Cámara` (lista visual),
  - `Micrófono` (lista visual).
- Chips de estado vivos:
  - cámara: verde/rojo,
  - micrófono: verde/rojo.
- Footer de acciones:
  - CTA principal progresivo,
  - acción secundaria discreta “Reintentar detección” (si hiciera falta).

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `#entryOverlay` + `entry-card` | `backend/interfaz_usuario_app/index.html` | Adaptar | Patrón de entrada ya validado UX | `screenSetup` en `comunicacion` |
| `renderEntryState()` | `backend/interfaz_usuario_app/app.js` | Adaptar | Modelo de CTA progresivo por estado | `renderSetupState()` |
| `entry-device-option` | `backend/interfaz_usuario_app/index.html` | Reutilizar tal cual (estética) | Visual moderna de selección | listas cámara/mic comunicación |
| `screenIntro` | `backend/comunicacion_app/index.html` | Descartar | Paso redundante | eliminar |
| `openPreviewBtn` + `SCREEN_PREVIEW` | `backend/comunicacion_app/index.html` / `app.js` | Descartar (visible UX) | Solicitud explícita: sin abrir preview | encapsular apertura stream sin paso separado |
| `<select>` nativos `videoDeviceSelect/audioDeviceSelect` | `backend/comunicacion_app/index.html` | Adaptar o descartar visualmente | No cumple patrón moderno objetivo | popover/lista tipo negociación |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion_app/index.html` | Secciones `screenIntro`, `screenPermissions`, `screenPreview` | ids de video solo si se reutilizan internamente | portada inicial + botón abrir preview | `screenSetup` único | Medio |
| `backend/comunicacion_app/app.js` | `SCREEN_*`, `SCREEN_ORDER`, handlers start/grant/open | `requestCapturePermissions`, `listCaptureDevices`, `openPreviewStream` | transición explícita a preview | estado/setup renderer y CTA progresivo | Medio |
| `backend/comunicacion_app/styles.css` | Bloques `.communication-*` entrada | tokens de color útiles | estética gris dominante de shell actual | estilo blanco limpio tipo negociación | Bajo |
| `backend/interfaz_usuario_app/app.js` | Lógica referencia (`renderEntryState`, device list) | patrón de decisión UX | modo write | blueprint de comportamiento | Bajo |

## 10) Riesgos o puntos delicados
- Permisos mixtos (mic OK, cámara KO): hay que definir estado parcial y mensaje claro.
- Si se elimina preview visible, la validación visual de cámara debe quedar resuelta en self-view posterior.
- No duplicar de forma descontrolada lógica de negociación; mejor portar patrón, no copiar todo el archivo.

## 11) Criterio de aceptación visual/UX
- El primer contacto ya es configuración AV, sin pantallas extra.
- El usuario ve un único CTA principal que evoluciona por estado.
- Cuando todo está correcto, CTA pasa a `Empezar` y avanza.
- No existe ningún rastro de modo texto o “Abrir preview”.
