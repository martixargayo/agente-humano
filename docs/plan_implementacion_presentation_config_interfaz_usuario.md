# 1. Resumen ejecutivo del plan de implementación

## Objetivo

Introducir `presentation_config` en `interfaz_usuario` con el **menor riesgo posible**, manteniendo intacta la frontera con la capa cognitiva. El objetivo no es rediseñar la aplicación, sino añadir una capa de presentación por contexto que permita variar únicamente:

1. `.glb` del avatar
2. background/fondo
3. cámara, framing y transform
4. calibración técnica del avatar (`mouth`, `neck`, `eyes/blink`, `lipsync`, tuning equivalente)
5. motion del avatar
6. voz del personaje/contexto

Todo lo demás debe permanecer común/global.

## Propuesta final de fases

Recomiendo una implementación en **3 fases**. No porque haga falta sobreingeniería, sino porque el riesgo real del repo está concentrado en dos zonas distintas:

- el **orden de arranque** del runtime frente al bootstrap backend;
- y la **externalización de calibración técnica del mesh** hoy hardcodeada en `runtime.js`.

Dividirlo en 3 fases permite aislar esos riesgos:

### Fase 1 — Infraestructura mínima segura

Se introduce `presentation_config` en backend/frontend, se cambian los defaults del runtime y se corrige el orden de arranque para que el avatar no nazca antes de recibir la config contextual. En esta fase solo se externalizan:

- `theme`
- `background`
- `avatar.model`
- `avatar.camera`
- `avatar.transform`
- `voice` básica

### Fase 2 — Calibración técnica del avatar

Se externaliza de forma controlada la parte dependiente del mesh:

- `mouth`
- `neck`
- `eyes/blink`
- `mouth_render`
- `lipsync`

### Fase 3 — Motion y refinamientos de escena/voz

Se saca a `presentation_config` la parte de motion y los ajustes de escena/voz que sí pertenecen a presentación, dejando el motor compartido intacto.

## Principios que el plan protege explícitamente

Este plan **no debe tocar**:

- orquestación de negociación
- prompts
- evaluadores
- session binding cognitivo
- cómo entra la información al pipeline de negociación
- cómo se resuelven turnos
- cómo funciona el sistema multicontexto cognitivo existente

Y además protege estas decisiones:

- `presentation_config` se resuelve con **defaults globales**, no heredando del baseline;
- `baseline_current` y `validacion_multicontexto` siguen compartiendo hoy la misma presentación efectiva;
- `interfaz_usuario` sigue siendo una **única app** con una piel contextual, no apps divergentes por contexto.

---

# 2. Fase 1

## Objetivo de la fase

Montar la infraestructura mínima segura para soportar `presentation_config` sin tocar lógica cognitiva y sin dejar que el runtime 3D arranque antes de tener contexto resuelto.

El objetivo operativo al terminar esta fase es:

- el backend ya devuelve `presentation_config`, `context_id` y `public_slug` en el bootstrap;
- el frontend ya espera esa respuesta antes de arrancar el runtime;
- el runtime ya consume defaults globales + overrides resueltos;
- ya se puede variar por contexto `.glb`, fondo, cámara, transform y voz básica;
- si un contexto no define nada, el sistema funciona con defaults globales explícitos.

## Archivos nuevos

### 1. `backend/interfaz_usuario/presentation_defaults.json`

Aquí pondría los defaults globales de presentación. Debe contener solo aquello que pertenece a presentación y que hoy es común a todos los contextos:

- `theme.shell_theme`
- `background`
- `avatar.model.url`
- `avatar.camera`
- `avatar.transform`
- `voice.voice_id`
- `voice.format`
- `voice.speaking_rate` si decidimos exponerlo ya

**Por qué aquí:** porque el fallback correcto ya está decidido: defaults globales explícitos, no baseline.

### 2. `backend/interfaz_usuario/presentation_models.py`

Crearía modelos tipados para el contrato de `presentation_config` devuelto por bootstrap. No hace falta modelar toda la fase 2 todavía; basta con el shape mínimo de la fase 1.

Ejemplo de bloques iniciales:

- `PresentationThemeConfig`
- `PresentationBackgroundConfig`
- `PresentationAvatarModelConfig`
- `PresentationCameraConfig`
- `PresentationTransformConfig`
- `PresentationVoiceConfig`
- `PresentationConfig`

**Por qué:** evita que `ensure_session()` empiece a devolver dicts ad hoc difíciles de evolucionar.

### 3. `backend/interfaz_usuario/presentation_resolver.py`

Añadiría un resolvedor específico de presentación con dos responsabilidades muy acotadas:

1. leer `presentation_defaults.json`;
2. cargar overrides contextuales desde la carpeta del contexto si existen;
3. hacer merge y devolver `PresentationConfig` normalizado.

El resolvedor no debe conocer prompts ni pipeline; solo paths de contexto y presentación.

### 4. `backend/negociacion/contexts/<context_id>/presentation/presentation_config.json`

Crearía la estructura en:

- `backend/negociacion/contexts/baseline_current/presentation/presentation_config.json`
- `backend/negociacion/contexts/validacion_multicontexto/presentation/presentation_config.json`

En esta fase pueden estar vacíos o contener solo `{}` / metadatos mínimos.

**Decisión importante:** sí conviene crear ya la estructura para ambos contextos, aunque hoy compartan la misma presentación efectiva. Eso deja clara la arquitectura futura sin duplicar defaults en cada contexto.

### 5. `backend/negociacion/contexts/<context_id>/presentation/assets/`

Prepararía la carpeta de assets contextuales, aunque en la fase 1 ambos contextos quizá no la usen aún:

- `presentation/assets/` para futuros `.glb` y backgrounds.

## Archivos modificados

### 1. `backend/interfaz_usuario/models.py`

Ampliaría el contrato del bootstrap. Hay dos caminos razonables:

- añadir un response model nuevo para bootstrap;
- o tipar explícitamente el dict devuelto por `ensure_session()`.

Yo haría lo primero: introducir un `SessionBootstrapResponse` con:

- `user_id`
- `session_id`
- `trace_count`
- `last_updated`
- `conversation_id`
- `previous_response_id`
- `context_id`
- `public_slug`
- `presentation_config`

**Por qué:** hoy bootstrap es el handshake oficial y es el sitio natural para inyectar la config de presentación resuelta.

### 2. `backend/interfaz_usuario/__init__.py`

Ajustaría el endpoint `/sessions/bootstrap` para devolver el response model nuevo. No cambiaría la semántica del endpoint ni añadiría rutas nuevas de negocio aquí.

### 3. `backend/interfaz_usuario/services.py`

En `ensure_session()` haría el cambio más importante de backend:

- después de fijar o validar el contexto con la lógica actual, resolvería el contexto oficial completo;
- llamaría a `presentation_resolver.resolve_presentation_config(...)`;
- devolvería `context_id`, `public_slug` y `presentation_config` junto al resto del payload.

**No tocaría** `run_turn()` en esta fase salvo que fuera estrictamente necesario para voz contextual, y mi recomendación es **no tocarlo** todavía. La voz puede resolverse en bootstrap y consumirse desde el frontend al invocar `/tts`, sin tocar el pipeline de negociación.

### 4. `backend/negociacion/contexts/models.py`

Añadiría, si hace falta, un puntero opcional a `presentation_dir` o un helper equivalente en el resolved context. No metería la config de presentación aquí; solo un path o metadata mínima.

### 5. `backend/negociacion/contexts/resolver.py`

Lo tocaría lo mínimo:

- para exponer `context_dir` de forma reutilizable si ya no bastara con lo actual;
- opcionalmente para añadir `presentation_dir` a `ResolvedNegotiationContext`.

**No mezclaría** la resolución cognitiva con el merge de presentación dentro de este archivo; mejor un resolver aparte.

### 6. `backend/api/app.py`

Añadiría una ruta dedicada para servir assets de presentación contextuales, por ejemplo:

- `/interfaz_usuario/context-assets/{context_id}/{asset_path:path}`

Esa ruta debería:

- resolver el contexto oficial con el resolver existente;
- limitar el path a la carpeta `presentation/assets/` del contexto;
- servir `.glb`, imágenes y otros assets permitidos.

**Por qué aquí:** los assets de presentación por contexto pertenecen a contextos oficiales, no a `backend/interfaz_usuario_app`.

### 7. `backend/interfaz_usuario_app/avatar_runtime/config.js`

Convertiría `AVATAR_RUNTIME_CONFIG` en algo como `AVATAR_RUNTIME_DEFAULTS` o equivalente. Ya no debe representar la config final del avatar, sino solo los defaults globales del runtime/frontend si fueran necesarios como fallback local adicional.

En esta fase, el contenido debería alinearse con `presentation_defaults.json` y no introducir una segunda fuente de verdad contradictoria.

### 8. `backend/interfaz_usuario_app/avatar_runtime/bootstrap.js`

Aquí haría el cambio clave de secuencia:

- dejaría de autoarrancar el runtime al cargar el módulo;
- exportaría una función explícita, por ejemplo `initAvatarRuntime({ stageEl, presentationConfig })`;
- opcionalmente añadiría `destroyAvatarRuntime()` si vemos valor en recargar el escenario en el futuro.

**Motivo:** hoy el runtime nace demasiado pronto con `AVATAR_RUNTIME_CONFIG` fija; eso rompe la idea misma de `presentation_config` contextual.

### 9. `backend/interfaz_usuario_app/app.js`

En esta fase introduciría una secuencia de init explícita:

1. leer `public_slug` de la URL como hoy;
2. llamar a `/api/interfaz_usuario/sessions/bootstrap`;
3. recibir `context_id`, `public_slug`, `presentation_config`;
4. aplicar al DOM el `theme/background` superficial;
5. arrancar el runtime con `initAvatarRuntime(...)` usando la config ya resuelta;
6. después enlazar readiness del runtime y continuar con el resto del init de UI.

Además, cambiaría `requestTTS(text)` para aceptar opcionalmente `voiceConfig`, por ejemplo:

- `requestTTS(text, presentationVoice)`

sin tocar el contrato del pipeline de negociación.

### 10. `backend/interfaz_usuario_app/index.html`

Lo tocaría lo mínimo:

- eliminar el autoarranque implícito del runtime vía script que ejecuta side effects al cargar;
- mantener el import del módulo si hace falta, pero sin inicialización automática;
- quizá dejar hooks CSS/DOM más claros para aplicar background/theme después del bootstrap.

**No cambiaría** la estructura base del DOM.

### 11. `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

En esta fase solo externalizaría lo de bajo riesgo:

- `modelUrl`
- `backgroundImageUrl` o el equivalente ya normalizado
- `camera`
- `controlsTarget`
- `controlsLocked`
- `transform`

No sacaría todavía `MouthTuning`, `NeckTuning`, `EyeBlinkTuning`, `MouthRenderTuning` ni `MotionConfig`.

## Cambios exactos por archivo

### Backend

- **`backend/interfaz_usuario/services.py`**: ampliaría `ensure_session()` para devolver `presentation_config`, `context_id` y `public_slug`, porque hoy ese bootstrap ya es el handshake oficial y es el sitio natural para inyectar la config resuelta.
- **`backend/api/app.py`**: añadiría una ruta para servir assets de presentación contextuales, porque los nuevos `.glb` y fondos no deberían colgar de `interfaz_usuario_app` si pertenecen a contextos oficiales.
- **`backend/interfaz_usuario/presentation_resolver.py`**: centralizaría merge de defaults globales + overrides por contexto, con validación y normalización.

### Frontend

- **`backend/interfaz_usuario_app/avatar_runtime/bootstrap.js`**: dejaría de autoarrancar el runtime al cargar el módulo y lo convertiría en una función explícita de inicialización llamada por `app.js` después del bootstrap backend.
- **`backend/interfaz_usuario_app/app.js`**: introduciría una fase explícita de init: primero bootstrap backend, luego aplicación de background/theme, luego arranque del avatar runtime con config ya resuelta.
- **`backend/interfaz_usuario_app/avatar_runtime/config.js`**: convertiría el objeto actual en defaults globales del runtime en lugar de config final.
- **`backend/interfaz_usuario_app/avatar_runtime/runtime.js`**: en una primera fase solo externalizaría `model/background/camera/transform` y dejaría mouth/blink/motion para fases posteriores por riesgo de dependencia con el mesh.

## Contrato/resultados esperados al terminar la fase

Al terminar Fase 1, el bootstrap debería devolver algo así:

```json
{
  "user_id": "u_interfaz",
  "session_id": "interfaz-main",
  "trace_count": 0,
  "last_updated": "...",
  "conversation_id": null,
  "previous_response_id": null,
  "context_id": "baseline_current",
  "public_slug": "negociacion",
  "presentation_config": {
    "theme": { "shell_theme": "realistic" },
    "background": { "type": "none", "url": null },
    "avatar": {
      "model": { "url": "/interfaz_usuario/context-assets/baseline_current/avatar.glb" },
      "camera": { "fov": 40, "position": [0, 0.22, 3.5], "target": [0, 0.14, 0], "controls_locked": true },
      "transform": { "offset": [0, 0, 0], "scale": 1.0 }
    },
    "voice": { "voice_id": "cedar", "format": "wav", "speaking_rate": 1.1 }
  }
}
```

## Qué sigue siendo común/global

Sigue siendo común/global:

- HTML shell
- overlay de entrada
- barra inferior
- flujo hablar/escribir
- selector de micrófono
- feedback/report UI
- bootstrap de turnos
- wiring STT/TTS
- API pública del runtime
- estados `IDLE/LISTENING/THINKING/SPEAKING`
- negociación/orquestación/pipeline

## Qué ya pasa a ser específico por contexto

Pasa a ser específico por contexto:

- `avatar.model.url`
- `background`
- `avatar.camera`
- `avatar.transform`
- `voice.voice_id` y parámetros sonoros de presentación básicos

## Riesgos

### Riesgo 1 — Secuencia de arranque

Cambiar el orden de init puede romper `scenarioReady`, overlay de entrada o wiring de `window.__avatarRuntime`.

**Mitigación:** mantener la API pública del runtime y hacer que `app.js` cree el runtime una sola vez, antes de enlazar `bindRuntimeReadiness()`.

### Riesgo 2 — Doble fuente de verdad de defaults

Si `presentation_defaults.json` y `config.js` divergen, el sistema se vuelve ambiguo.

**Mitigación:** usar `presentation_defaults.json` como fuente de verdad del backend y dejar `config.js` reducido a defaults técnicos mínimos o eliminar su autoridad semántica.

### Riesgo 3 — Assets contextuales mal servidos

Riesgo de path traversal o rutas rotas.

**Mitigación:** servir assets solo desde `presentation/assets/` de contextos oficiales, validando el contexto con el resolver existente.

## Cómo probarlo

1. Abrir `/interfaz_usuario/negociacion`.
2. Verificar que la UI sigue cargando y que el avatar aparece.
3. Confirmar que el runtime solo arranca tras el bootstrap exitoso.
4. Confirmar en network que `/api/interfaz_usuario/sessions/bootstrap` devuelve `context_id`, `public_slug` y `presentation_config`.
5. Confirmar que si `presentation/presentation_config.json` está vacío, se usan defaults globales.
6. Confirmar que TTS sigue funcionando y que `requestTTS()` puede recibir `voice_id` contextual sin tocar negociación.

---

# 3. Fase 2

## Objetivo de la fase

Externalizar la calibración técnica del avatar dependiente del mesh sin romper el runtime actual ni asumir que cualquier `.glb` arbitrario funcionará solo con cambiar la ruta.

Esta fase existe porque hoy gran parte de la “personalidad técnica” del avatar está incrustada en `runtime.js`:

- `MouthTuning`
- `NeckTuning`
- `EyeBlinkTuning`
- `MouthRenderTuning`
- parte del lipsync

Eso no debe salir a config de golpe ni sin schema, porque depende directamente de la geometría del modelo.

## Archivos nuevos

### 1. Ampliación de `backend/interfaz_usuario/presentation_models.py`

Añadiría bloques nuevos:

- `PresentationAvatarCalibrationMouthConfig`
- `PresentationAvatarCalibrationNeckConfig`
- `PresentationAvatarCalibrationEyesConfig`
- `PresentationAvatarCalibrationMouthRenderConfig`
- `PresentationAvatarCalibrationLipSyncConfig`

### 2. Ampliación de `presentation_defaults.json`

Añadiría los defaults globales que reflejan el tuning actual del avatar compartido.

### 3. Ampliación de `presentation/presentation_config.json` por contexto

Permitiría overrides parciales de calibración solo cuando un contexto use un mesh distinto o necesite ajuste específico.

## Archivos modificados

### 1. `backend/interfaz_usuario/presentation_resolver.py`

Extendería el merge para soportar:

- `avatar.calibration.mouth`
- `avatar.calibration.neck`
- `avatar.calibration.eyes`
- `avatar.calibration.mouth_render`
- `avatar.calibration.lipsync`

Con merge profundo, no reemplazo bruto de todo el subárbol.

### 2. `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

Haría un refactor quirúrgico, no una reescritura:

- extraería las constantes `MouthTuning`, `NeckTuning`, `EyeBlinkTuning`, `MouthRenderTuning` a una capa `resolvedCalibration` derivada de `config.avatar.calibration`;
- mantendría iguales los algoritmos de render/blink/lipsync;
- cambiaría solo la procedencia de valores, no la lógica matemática;
- dejaría defaults internos como red de seguridad durante la migración, idealmente con un helper `resolveCalibrationDefaults(config)`.

**Clave:** en esta fase se externalizan los números, no el comportamiento del engine.

### 3. `backend/interfaz_usuario_app/avatar_runtime/config.js`

Si sigue existiendo, lo reduciría aún más a defaults internos de compatibilidad, porque la autoridad ya debería estar en `presentation_config`.

## Cambios exactos por archivo

- **`runtime.js`**: reemplazaría las constantes hardcodeadas por lecturas de `config.avatar.calibration.*`, sin tocar el algoritmo de blink/mouth/lipsync salvo para leer valores parametrizados.
- **`presentation_resolver.py`**: aplicaría defaults globales de calibración cuando el contexto no defina override.
- **`presentation_models.py`**: tiparía estrictamente rangos y campos para evitar configs incompletas o incoherentes.

## Contrato/resultados esperados al terminar la fase

Al terminar Fase 2, `presentation_config` ya debe permitir algo como:

```json
{
  "avatar": {
    "calibration": {
      "mouth": {
        "center_x": -0.045,
        "center_y": 0.16,
        "width": 0.18,
        "height": 0.14,
        "curve": 0.0
      },
      "neck": {
        "center_x": -0.0554,
        "width": 0.3289,
        "top_y": -0.3029,
        "bottom_y": -0.5299,
        "curve": -0.1845,
        "neck_pivot_y": -0.5299,
        "body_pivot_y": -0.6499
      },
      "eyes": {
        "left": { "...": "..." },
        "right": { "...": "..." }
      },
      "mouth_render": {
        "mesh_fade": 0.42,
        "mesh_feather": 0.12,
        "points_on": 0.05,
        "points_off": 0.032
      },
      "lipsync": {
        "talk_amp_top": 0.024,
        "talk_amp_bottom": 0.075,
        "talk_freq": 24.0,
        "lip_depth_amp": 0.1,
        "rest_open": 0.03,
        "attack": 26.0,
        "release": 12.0
      }
    }
  }
}
```

## Qué sigue siendo común/global

Sigue siendo común/global:

- algoritmo de render del avatar;
- shaders;
- lifecycle del runtime;
- API pública del runtime;
- flujo de turnos;
- bootstrap de sesión;
- STT/TTS plumbing;
- toda la lógica cognitiva.

## Qué ya pasa a ser específico por contexto

Pasa a ser específico por contexto:

- calibración geométrica de boca;
- pivots/cuello;
- geometría de blink/ojos;
- parámetros de mouth render;
- amplitudes y timings de lipsync dependientes del modelo.

## Riesgos

### Riesgo 1 — Dependencia fuerte con el mesh actual

Si se expone mal la calibración, un nuevo `.glb` puede verse peor o romper blink/lipsync.

**Mitigación:** externalizar solo parámetros observados ya existentes, con defaults globales completos y validación tipada.

### Riesgo 2 — Hacer el schema demasiado abierto

Un schema excesivamente libre generaría configs difíciles de soportar.

**Mitigación:** limitarse a los knobs reales ya presentes en `runtime.js`.

## Cómo probarlo

1. Mantener un contexto con calibración vacía y comprobar que todo sigue igual.
2. Crear un override controlado en un contexto de prueba para mover levemente `mouth.center_x` o `camera.target`.
3. Confirmar que blink, lipsync y mouth render siguen funcionando.
4. Verificar que audio/mic/turnos siguen intactos.

---

# 4. Fase 3

## Objetivo de la fase

Abrir motion, refinamientos de escena y los parámetros de voz que sí pertenecen a presentación, sin convertir el runtime en un saco de knobs arbitrarios.

Recomiendo dejar esto para Fase 3 porque no es necesario para desbloquear la arquitectura, pero sí útil para completar la capa de presentación prevista.

## Archivos nuevos

No necesariamente requiere archivos nuevos si `presentation_models.py`, `presentation_defaults.json` y `presentation_resolver.py` ya existen y solo se amplían.

## Archivos modificados

### 1. `backend/interfaz_usuario/presentation_models.py`

Añadiría:

- `PresentationAvatarMotionConfig`
- subbloques `head`, `body`, `micro`, `nod`, `body_bob`
- si aplica, ampliaciones de `PresentationVoiceConfig`

### 2. `backend/interfaz_usuario/presentation_resolver.py`

Soportaría merge para:

- `avatar.motion`
- `scene.lighting`
- parámetros extra de `voice`

### 3. `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

Externalizaría desde `MotionConfig` solo las amplitudes y timings ya existentes:

- `head.ampYaw/ampPitch/ampRoll`
- `body.*`
- `micro.*`
- `nod.*`
- `body_bob.*`

**No sacaría** `MotionState`, seeds, scheduler interno ni lógica de interpolación; eso sigue siendo motor común.

### 4. `backend/interfaz_usuario_app/app.js`

Ampliaría el uso de `presentation_config.voice` para pasar al `/tts`:

- `voice`
- quizá `format`
- quizá `speed`

Siempre que el backend ya los soporte sin tocar negociación.

### 5. `backend/api/app.py`

Tocaría `/tts` solo si hace falta aceptar de forma explícita `speed` o `instructions` acotadas desde el frontend. Mi recomendación es:

- permitir `voice` y quizá `format`/`speed`;
- **no** exponer instrucciones libres arbitrarias desde frontend.

## Cambios exactos por archivo

- **`runtime.js`**: movería `MotionConfig` a `config.avatar.motion`, pero dejaría `MotionState` y la lógica de animación dentro del motor.
- **`app.js`**: haría que `requestTTS()` use `presentation_config.voice` si existe.
- **`api/app.py`**: mantendría proveedor/caché/prefetch/warmup globales y solo permitiría overrides seguros de presentación.

## Contrato/resultados esperados al terminar la fase

Al terminar Fase 3, `presentation_config` ya debería cubrir el alcance completo pedido:

- `.glb`
- background
- cámara / framing / transform
- calibración técnica del avatar
- motion
- voz

## Qué sigue siendo común/global

Sigue siendo común/global:

- DOM y shell de la app;
- interacción hablar/escribir;
- selector de micrófono;
- feedback/report UI;
- estados y lifecycle del runtime;
- provider TTS/STT y plumbing técnico;
- pipeline de negociación.

## Qué ya pasa a ser específico por contexto

Pasa a ser específico por contexto:

- motion del personaje;
- lighting/scene presentation que afecte al look;
- voz final del personaje dentro de límites seguros.

## Riesgos

### Riesgo 1 — Exponer demasiados knobs de motion

Se puede degradar la naturalidad del avatar.

**Mitigación:** exponer solo los parámetros que ya existen en `MotionConfig`, no la lógica interna.

### Riesgo 2 — Mezclar voz con persona cognitiva

Si se exponen instrucciones libres, presentation puede contaminar razonamiento/persona.

**Mitigación:** permitir solo `voice_id`, `format`, `speed` y quizá un `style` acotado si el proveedor lo soporta claramente.

## Cómo probarlo

1. Definir un override pequeño de motion en un contexto de prueba y comparar idle/head motion.
2. Verificar que la voz cambia por contexto sin alterar turnos ni respuestas.
3. Probar fallback a defaults globales si faltan bloques `motion` o `voice`.

---

# 5. Archivos exactos a tocar en cada fase

## Fase 1

### Nuevos

- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/negociacion/contexts/baseline_current/presentation/presentation_config.json`
- `backend/negociacion/contexts/baseline_current/presentation/assets/`
- `backend/negociacion/contexts/validacion_multicontexto/presentation/presentation_config.json`
- `backend/negociacion/contexts/validacion_multicontexto/presentation/assets/`

### Modificados

- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/negociacion/contexts/models.py`
- `backend/negociacion/contexts/resolver.py`
- `backend/interfaz_usuario_app/index.html`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/avatar_runtime/bootstrap.js`
- `backend/interfaz_usuario_app/avatar_runtime/config.js`
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

## Fase 2

### Nuevos

- ninguno obligatorio adicional, salvo quizá fixtures/docs de calibración

### Modificados

- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`
- `backend/negociacion/contexts/*/presentation/presentation_config.json`

## Fase 3

### Nuevos

- ninguno obligatorio

### Modificados

- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`
- `backend/interfaz_usuario_app/app.js`
- `backend/api/app.py` (solo si se amplía `voice` de forma segura)
- `backend/negociacion/contexts/*/presentation/presentation_config.json`

---

# 6. Qué NO tocaría

No tocaría, salvo descubrimiento excepcional durante implementación:

- `backend/negociacion/orchestration/*`
- prompts en `backend/negociacion/contexts/*/prompts/`
- assets cognitivos (`persona.json`, `negotiation_brief.json`, `phase_cards.json`, `phase_classifier_card.json`)
- evaluación en `backend/negociacion/contexts/*/evaluation/`
- `backend/negociacion/contexts/session_binding.py` en su lógica cognitiva
- `backend/interfaz_usuario/services.py::run_turn()` para lógica de negocio
- pipeline de turnos
- reglas de feedback/evaluación
- estructura base de `index.html`

En particular:

- no cambiaría cómo se resuelve el contexto cognitivo;
- no usaría baseline como herencia mágica de presentación;
- no convertiría cada contexto en una variante de aplicación distinta.

---

# 7. Riesgos por fase

## Fase 1

- romper el orden de arranque del runtime
- introducir ambigüedad entre defaults backend y defaults frontend
- errores al servir assets contextuales

## Fase 2

- romper blink/lipsync por parametrización incorrecta
- hacer demasiado flexible una calibración que en realidad depende del mesh

## Fase 3

- degradar naturalidad del motion
- contaminar la capa de presentación con instrucciones semánticas de voz

---

# 8. Validación por fase

## Validación Fase 1

- abrir `/interfaz_usuario/negociacion`
- abrir `/interfaz_usuario/negociacion-validacion`
- verificar que ambas URLs siguen cargando la misma UI base
- verificar que el bootstrap devuelve `presentation_config`
- verificar que el runtime no arranca antes del bootstrap
- verificar fallback a defaults globales si no hay overrides
- verificar que TTS sigue funcionando

## Validación Fase 2

- verificar que con calibración vacía el comportamiento es idéntico al actual
- verificar overrides controlados de `mouth`, `neck`, `eyes`, `lipsync`
- verificar que no se rompe audio, micro ni turnos

## Validación Fase 3

- verificar overrides de motion por contexto
- verificar voz contextual por contexto
- verificar que si faltan `motion` o `voice` se usan defaults globales
- verificar que baseline y validación siguen compartiendo presentación efectiva si sus overrides están vacíos

---

# 9. Veredicto final

El orden correcto de implementación con menor riesgo es:

1. **Primero** introducir `presentation_config` como contrato real de bootstrap y corregir el orden de arranque del runtime. Esa es la pieza crítica porque hoy el avatar nace antes de conocer el contexto.  
2. **Después** externalizar la calibración técnica del avatar, pero solo como parametrización de valores ya existentes en `runtime.js`, sin reescribir el motor.  
3. **Por último** abrir motion y refinamientos de escena/voz que sí pertenecen a presentación, manteniendo el engine compartido.

La clave del plan es que deja muy claro dónde tocar y dónde no tocar:

- **sí tocar** bootstrap, runtime init, defaults globales de presentación, resolver contextual, assets contextuales y parámetros de avatar/voz que pertenecen a presentación;
- **no tocar** negociación, prompts, evaluadores, session binding cognitivo ni flujo de turnos.

Para el caso real actual:

- `baseline_current` y `validacion_multicontexto` deben tener estructura `presentation/` preparada;
- hoy pueden seguir compartiendo la misma presentación efectiva;
- y el fallback debe venir siempre de `presentation_defaults.json`, nunca del baseline como herencia implícita.

Ese es el mínimo refactor que deja la arquitectura bien montada, evita hacks, no rompe el sistema actual y permite añadir mañana un tercer contexto con su propia skin de avatar/presentación sin contaminar la lógica cognitiva.
