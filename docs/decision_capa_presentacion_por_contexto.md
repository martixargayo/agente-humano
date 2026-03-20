# 1. Qué debería ser común/global en la UI de interfaz_usuario

## Resumen ejecutivo

La frontera correcta en este repo no es simplemente entre “config visual” y “config cognitiva”, sino entre tres capas distintas:

1. **Motor/UI común global**: HTML base, overlays, barra inferior, selector de micrófono, flujo hablar/escribir, bootstrap frontend/backend, eventos del runtime y wiring con STT/TTS. Esto debe seguir siendo compartido por todos los contextos porque define la superficie pública y el contrato operativo de `interfaz_usuario`, no la identidad del personaje.  
2. **Presentación por contexto**: modelo `.glb`, fondo, cámara, framing, transform, motion y voz/identidad sonora. Esto sí debe poder variar por contexto porque describe cómo “se ve y se oye” el personaje en cada escenario sin tocar la lógica del flujo.  
3. **Calibración técnica del avatar/modelo**: boca, cuello, blink, lipsync y cualquier tuning geométrico dependiente del mesh. Aunque hoy vive hardcodeado en `runtime.js`, conceptualmente no es motor global ni lógica de negocio: es configuración técnica específica del avatar y debe viajar con la presentación del contexto o del modelo.  

La recomendación final es nombrar esta capa como **`presentation_config`**, no `visual_config`, porque en el caso real del repo la voz encaja mejor ahí que en la capa cognitiva. Dentro de `presentation_config` conviene distinguir explícitamente entre:

- `scene` / `background` / `camera` / `theme`
- `avatar.model` / `avatar.transform`
- `avatar.calibration`
- `avatar.motion`
- `voice`

Y mantener fuera de ella: prompts, persona cognitiva, reglas de negociación, pipeline, evaluación y estado de sesión.

Para el caso actual `baseline_current` y `validacion_multicontexto`, la opción más limpia es:

- conservar **defaults globales comunes del motor**;
- introducir **estructura preparada de presentation por contexto**;
- y dejar hoy ambos contextos con **overrides vacíos o mínimos**, porque siguen usando la misma presentación real.

Eso evita sobreacoplar el baseline como herencia mágica, deja el repo listo para divergencias futuras y mantiene visible que hoy ambos contextos comparten la misma piel de UI.

## 1.1. Qué parte de la UI actual es claramente global y común

### a) `index.html` como shell único de la aplicación

`backend/interfaz_usuario_app/index.html` define la carcasa completa de la experiencia: escenario `#stage`, contenedor de fondo `#bg`, overlay de entrada, barra inferior, reply container, selector de micrófono, loading/evaluación y todos los nodos DOM que `app.js` cablea después. Esa estructura no representa un contexto concreto, sino la **superficie pública estable** de `interfaz_usuario`. Debe seguir siendo global.

### b) `app.js` como orquestador de interacción y estado de UI

`backend/interfaz_usuario_app/app.js` resuelve:

- lectura de `public_slug` desde URL;
- bootstrap de sesión contra `/api/interfaz_usuario/sessions/bootstrap`;
- alternancia hablar/escribir;
- captura de micrófono;
- selector de dispositivo de audio;
- reproducción TTS;
- transición de modos del avatar (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`);
- polling/reporting de feedback.

Todo eso es **flujo operativo compartido**. Aunque algunas etiquetas visuales o acentos pudieran tematizarse más adelante, el wiring principal debe seguir siendo común porque mantiene la coherencia de la app y evita que cada contexto se convierta en una miniaplicación distinta.

### c) Contrato frontend/backend de bootstrap y turnos

`backend/interfaz_usuario/__init__.py`, `backend/interfaz_usuario/models.py` y `backend/interfaz_usuario/services.py` exponen el contrato de:

- `POST /api/interfaz_usuario/sessions/bootstrap`
- `POST /api/interfaz_usuario/negociacion/new_conversation`
- `POST /api/interfaz_usuario/negociacion/turn`

Ese contrato debe seguir siendo global. Lo correcto es enriquecerlo con una sección de presentación resuelta, no fragmentarlo por contexto.

### d) Eventos públicos del runtime

`avatar-runtime-ready`, `avatar-runtime-error`, `window.__avatarRuntime`, `setMode()` y `setTalkLevel()` son parte del **API del motor** entre `app.js` y `runtime.js`. Esa interfaz debe seguir siendo común. Si cambia, rompe toda la UI; si permanece estable, permite que el motor reciba distinta presentation config sin que `app.js` conozca detalles internos del avatar.

### e) Wiring con STT/TTS como infraestructura común

En `app.js` y `backend/api/app.py` existen la captura STT, warmup, reproducción TTS y endpoints `/transcribe`, `/tts`, `/tts_openai`. Este wiring debe seguir siendo infraestructura global. Lo que sí puede variar por contexto es la **identidad vocal** o algunos parámetros de salida, no el canal técnico.

### f) Sistema de overlays, feedback y controles de interacción

Entry overlay, listening glow, loading de evaluación, feedback report view, finish button, input orb, popovers de audio y estructura de botones pertenecen a la UX común del producto. No deberían fragmentarse por contexto salvo microtematización superficial muy justificada, porque mezclar variaciones de layout/comportamiento con diferencias de avatar complica mantenimiento y pruebas.

## 1.2. Qué partes globales NO conviene abrir por contexto aunque hoy estén hardcodeadas

Hay hardcodes que parecen “configurables”, pero conceptualmente siguen siendo motor común:

- importmap de Three.js en `index.html`;
- creación de `THREE.Scene`, `WebGLRenderer`, `OrbitControls` en `runtime.js`;
- API pública `createAvatarRuntime()`;
- lifecycle de readiness/error;
- smoothing base de lipsync en `computeLipsyncLevel()`;
- infraestructura de resize/render loop/debug hooks.

Aunque parte de esos valores internos pueda necesitar tuning, no conviene exponer cada detalle por contexto porque dejaría de existir un runtime compartido y pasaríamos a tener forks implícitos del motor.

---

# 2. Qué debería poder variar por contexto

## 2.1. Taxonomía real de lo que sí pertenece a la capa contextual

La capa que este repo necesita no es solo visual: describe la **presentación del personaje y del escenario**. Incluye cinco grupos distintos.

### A. Presentación escénica

Es la piel externa del escenario:

- background image / treatment;
- overlays visuales ligados al escenario, si algún día se habilitan;
- theme superficial del stage;
- lighting cuando afecte al look del personaje/escena.

Esto sí es contextual porque cambia cómo se percibe el mismo flujo sin alterar la mecánica de la UI.

### B. Presentación del avatar

Es la identidad tridimensional visible:

- `model_url` del `.glb`;
- transform inicial del avatar (offset, scale, quizá rotation si se necesitara);
- framing/camera target/posición.

Esta categoría debe variar por contexto porque un nuevo personaje o escena puede necesitar otro encuadre incluso manteniendo el mismo flujo conversacional.

### C. Calibración técnica dependiente del modelo

Aquí está la frontera que más importa aclarar. Los parámetros de:

- `MouthTuning`;
- `NeckTuning`;
- `EyeBlinkTuning`;
- `MouthRenderTuning`;
- amplitudes específicas de lipsync que dependen del mesh;

no son “estilo libre”, sino **calibración técnica del avatar/modelo**. Deben poder variar por contexto si el contexto usa otro `.glb`, pero no deberían tratarse como knobs de producto que cualquiera toca a mano. Su lugar correcto es un subbloque técnico del presentation config, por ejemplo `avatar.calibration`.

### D. Motion tuning de personaje

`MotionConfig`, nods, bobbing y micro-motion describen la energía corporal del personaje. Esto sí puede variar por contexto porque forma parte de la presentación/acting del avatar. Aun así, debe mantenerse dentro de un rango acotado y apoyado en defaults globales para no degradar la naturalidad del runtime.

### E. Voz / presentación sonora

La voz usada por el personaje sí encaja en esta capa, siempre que hablemos de presentación y no de razonamiento:

- voz TTS (`voice`);
- quizá `speed`, `format`, o un `style` si el backend lo soporta;
- identidad vocal del personaje.

No debería mezclarse con prompts cognitivos. La voz es cómo suena el personaje al usuario, igual que el `.glb` es cómo se ve.

## 2.2. Qué categorías contextuales detecta el runtime actual

Aterrizado al repo actual, estas son las familias reales que hoy ya existen o están insinuadas:

### Avatar model

`modelUrl` ya existe en `backend/interfaz_usuario_app/avatar_runtime/config.js`. Es el candidato contextual más claro y de menor riesgo.

### Camera / framing

`camera`, `controlsTarget`, `controlsLocked`, `transform.scale` y `transform.offset` ya existen también en config. Esto confirma que el runtime ya tiene un punto natural para presentation config, aunque solo global.

### Scene / background

`backgroundImageUrl` existe en config, pero el HTML/CSS actual fuerza el theme `realistic` y apaga el fondo. Eso significa que la categoría es válida, pero aún no está bien conectada.

### Calibration / rig tuning

`MouthTuning`, `NeckTuning`, `EyeBlinkTuning` y `MouthRenderTuning` viven embebidos en `runtime.js`. Son contexto-específicos cuando cambia el mesh, pero hoy no tienen un contrato claro.

### Motion

`MotionConfig` y `MotionState` están dentro de `runtime.js`. El estado debe seguir siendo motor; la configuración de amplitudes/hold/ramp sí puede ir a presentation config.

### Voice

La voz hoy se resuelve en backend vía `/tts` y `DEFAULT_VOICE` / `payload.voice` en `backend/api/app.py`, mientras `app.js` usa `requestTTS(text)` sin pasar identidad contextual. Esto muestra que la voz es **configurable técnicamente**, pero aún no está integrada con el contexto. Es un buen candidato a moverse a la capa de presentación resuelta.

---

# 3. Cómo separar presentación, calibración de avatar y lógica común

## 3.1. Nombre conceptual correcto de la capa

Entre las alternativas propuestas:

- `ui_config` es demasiado amplio: sugiere que layout, botones y flujos completos también cambian por contexto.
- `visual_config` es demasiado estrecho: deja fuera voz y quizá otros aspectos sonoros del personaje.
- `avatar_presentation_config` es preciso para el avatar, pero demasiado estrecho para background/scene/theme.

La mejor opción para este repo es **`presentation_config`**.

### Por qué `presentation_config` encaja mejor

Porque la capa va a contener:

- lo que el usuario **ve** del personaje y la escena;
- y lo que el usuario **oye** del personaje;
- pero no la estructura completa de la aplicación ni la lógica del sistema.

Ese nombre obliga además a separar internamente lo que es:

- presentación de escena;
- presentación sonora;
- calibración técnica del avatar.

## 3.2. Taxonomía recomendada final

La capa `presentation_config` debería dividirse así:

### `theme`
Microtematización superficial del shell visual aplicable sin alterar DOM/UX.

### `background`
Imagen, gradiente, overlay y tratamiento del stage.

### `avatar`
Subárbol principal del personaje.

#### `avatar.model`
Ruta del `.glb` y metadatos básicos del asset.

#### `avatar.transform`
Scale, offset y quizá rotation inicial.

#### `avatar.camera`
Framing, position, target, fov, clipping, controls lock.

#### `avatar.calibration`
Parámetros dependientes del mesh:

- mouth zone;
- neck pivots/zones;
- eye blink geometry;
- mouth render tuning;
- lipsync parameters dependientes del modelo.

#### `avatar.motion`
Idle motion, micro motion, nods, breathing/body bob y otros rasgos cinéticos del personaje.

### `scene`
Luces u otros ajustes del entorno 3D que modulan la presentación.

### `voice`
Identidad vocal y parámetros TTS del personaje.

## 3.3. Qué NO entra en `presentation_config`

### Lógica cognitiva y de negocio

Debe quedar explícitamente fuera:

- prompts (`planner`, `executor`, `summarizer`, `phase_classifier`);
- `persona.json` como definición cognitiva del negociador;
- `negotiation_brief.json`;
- phase cards y phase classifier cards;
- reglas de negociación;
- condiciones de cierre;
- evaluación/rúbricas;
- pipeline/orchestration;
- estados de sesión/turnos;
- decisiones sobre cuándo crear nueva conversación;
- política de memoria o tracing.

### Layout y comportamiento base de la app

También debe quedar fuera, salvo necesidad futura muy fuerte:

- estructura DOM principal;
- overlays de entrada;
- bottom bar;
- flujo hablar/escribir;
- selector de micrófono;
- feedback/report UI;
- wiring de eventos;
- infraestructura STT/TTS.

Si eso se mete en la capa contextual, el repo pasaría de “contextos con distinta piel” a “aplicaciones divergentes”, que no es el objetivo actual.

## 3.4. Config común del runtime vs config específica de contexto

La frontera recomendada es esta:

### Config común del runtime

Debe vivir una vez y ser compartida:

- creación del renderer/scene/canvas;
- API pública del runtime;
- loop de animación;
- integración con `app.js`;
- estados `IDLE/LISTENING/THINKING/SPEAKING`;
- helpers debug;
- algoritmo base de suavizado y lifecycle.

### Config específica de contexto

Debe poder overridearse:

- assets (`.glb`, fondo);
- framing/cámara/transform;
- lights si afectan la presentación;
- motion tuning;
- calibración geométrica del modelo;
- voz TTS del personaje.

## 3.5. Matriz global vs específico de contexto

| Elemento / parámetro | Ubicación actual | Naturaleza real | ¿Global o por contexto? | Justificación | Riesgo si se context-specifica | Recomendación final |
|---|---|---|---|---|---|---|
| `index.html` shell | `backend/interfaz_usuario_app/index.html` | Infraestructura UI | Global | Es la superficie pública común y el DOM que cablea `app.js` | Alto: fragmenta la app | Mantener global |
| Entry overlay / bottom bar / reply container | `index.html` + `app.js` | UX común | Global | Define interacción base, no identidad contextual | Alto | Mantener global |
| Flujo hablar/escribir | `app.js` | UX común | Global | Debe ser consistente entre contextos | Alto | Mantener global |
| Selector de micrófono | `app.js` | Infraestructura UI | Global | No depende del personaje | Bajo-medio | Mantener global |
| Feedback/report UI | `feedback_report_view.js`, `app.js` | UX/common tooling | Global | Pertenece al producto, no al contexto | Medio | Mantener global |
| Bootstrap `/sessions/bootstrap` | `interfaz_usuario/services.py` | Contrato FE/BE | Global | Es handshake oficial de la superficie | Medio | Mantener global y ampliar payload |
| `window.__avatarRuntime` API | `bootstrap.js`, `runtime.js` | API de motor | Global | Debe ser estable para toda la app | Alto | Mantener global |
| Estados del avatar (`IDLE`, etc.) | `app.js`, `runtime.js` | Runtime común | Global | Son semántica compartida de interacción | Alto | Mantener global |
| `.glb` / `modelUrl` | `avatar_runtime/config.js` | Presentación avatar | Contexto | Define identidad visual del personaje | Bajo | Mover a `presentation_config.avatar.model` |
| Fondo / background | `index.html` + `config.js` | Presentación escena | Contexto | Afecta percepción del escenario | Bajo | Mover a `presentation_config.background` |
| Theme superficial | `index.html` | Presentación shell | Contexto limitado | Puede variar sin tocar UX base | Bajo | Permitir override ligero |
| Cámara (`fov`, `position`) | `config.js` | Presentación/framing | Contexto | Depende del avatar/encuadre | Bajo | Mover a `presentation_config.avatar.camera` |
| `controlsTarget` | `config.js` | Presentación/framing | Contexto | Ajusta encuadre del personaje | Bajo | Contextual |
| `controlsLocked` | `config.js` | Política runtime/UI | Global con override raro | Normalmente debe ser igual para todos | Medio | Mantener global por defecto; override excepcional |
| Transform `scale`/`offset` | `config.js` | Presentación avatar | Contexto | Depende del modelo usado | Bajo | Contextual |
| Luces (`key`, `rim`, `ambient`) | `runtime.js` | Presentación escena 3D | Contexto | Cambian el look del personaje | Medio | Contextual con defaults globales |
| `MouthTuning` | `runtime.js` | Calibración técnica modelo | Contexto/modelo | Depende de geometría del mesh | Medio | Mover a `avatar.calibration.mouth` |
| `NeckTuning` | `runtime.js` | Calibración técnica modelo | Contexto/modelo | Depende de pivots del avatar | Medio | Mover a `avatar.calibration.neck` |
| `EyeBlinkTuning` | `runtime.js` | Calibración técnica modelo | Contexto/modelo | Depende de ubicación real de ojos/párpados | Medio | Mover a `avatar.calibration.eyes` |
| `MouthRenderTuning` | `runtime.js` | Calibración + presentación técnica | Contexto/modelo | Depende del mesh y del efecto deseado | Medio-alto | Contextual, pero con schema acotado |
| Lipsync amplitudes/freq | `runtime.js` shaders/uniforms | Calibración técnica modelo | Contexto/modelo | Cambia con proporciones del avatar y voz | Medio | Mover a `avatar.calibration.lipsync` |
| MotionConfig | `runtime.js` | Presentación cinética | Contexto | Expresa personalidad corporal | Medio | Mover a `avatar.motion` |
| MotionState | `runtime.js` | Estado interno del motor | Global/runtime | Es estado vivo del loop, no config | Alto | Mantener interno |
| Resize/render loop | `runtime.js` | Motor común | Global | Infraestructura de engine | Alto | Mantener global |
| Debug edit flags | `runtime.js` URL params | Herramienta de desarrollo | Global | No es concern contextual | Bajo | Mantener fuera de presentation config |
| STT endpoints / grabación | `app.js`, `api/app.py` | Infraestructura audio | Global | No depende del contexto | Medio | Mantener global |
| `voice` TTS | `api/app.py` | Presentación sonora | Contexto | Define cómo suena el personaje | Bajo | Mover a `presentation_config.voice.voice_id` |
| `tts model` | `api/app.py` env | Infraestructura/proveedor | Global por defecto | Mejor centralizarlo salvo necesidad fuerte | Medio | Global con override muy controlado |
| `speed` / prosodia | hoy no expuesto | Presentación sonora | Contexto opcional | Puede formar parte del personaje | Bajo-medio | Contextual si backend lo soporta |
| `instructions` TTS | no existe como tal | Riesgo de mezcla | Normalmente no en esta capa | Puede contaminar con persona cognitiva | Alto | Evitar salvo micro-instrucciones sonoras estrictas |
| Prompts / persona cognitiva | `contexts/*/prompts`, `assets` | Lógica cognitiva | Nunca en esta capa | Pertenece al razonamiento/negociación | Muy alto | Mantener fuera |
| Session binding / tracing | `session_binding.py`, state | Infraestructura backend | Global | No es presentación | Alto | Mantener fuera |
| Reglas de evaluación | `evaluation/` | Negocio/QA | Global/contexto cognitivo, no presentación | No afecta apariencia | Alto | Mantener fuera |

## 3.6. Voz: qué parte es presentación y qué parte no

La voz merece una frontera propia.

### Sí pertenece a `presentation_config.voice`

- `voice_id` o nombre de voz del proveedor;
- `speaking_rate` si existe soporte técnico real;
- quizá `pitch`/`style` si el proveedor lo admite de forma estable;
- formato preferido de salida si afecta experiencia perceptible y no infraestructura general.

### Debe seguir global

- proveedor TTS (`OpenAI` actual);
- endpoint `/tts`;
- caché/prefetch;
- warmup;
- codec por defecto y plumbing general;
- manejo de errores/fallbacks.

### No debe mezclarse aquí

- instrucciones semánticas extensas del personaje;
- rasgos cognitivos del negociador;
- prompt engineering para cómo razona o persuade.

Si algún día se quiere una “identidad oral” más rica, debería modelarse como un bloque muy acotado de presentación, no como mini-prompt incrustado en TTS.

---

# 4. Cómo modelaría hoy baseline_current y validacion_multicontexto

## 4.1. Hecho observable actual

`baseline_current` y `validacion_multicontexto` están separados oficialmente a nivel de:

- `context_id`;
- `public_slug`;
- manifests;
- resolución de contexto;
- binding de sesión.

Pero hoy comparten exactamente la misma presentación porque `interfaz_usuario` sirve el mismo `index.html`, el mismo `app.js`, el mismo `bootstrap.js`, el mismo `AVATAR_RUNTIME_CONFIG` y los mismos hardcodes de `runtime.js`.

## 4.2. Estrategias posibles

### Estrategia A — Una sola config global compartida y ningún archivo contextual

**Ventaja:** mínimo trabajo inmediato.  
**Problema:** no deja trazada la frontera entre motor común y presentación contextual. En cuanto llegue el primer override, habrá que abrir esa estructura deprisa y con más riesgo.

### Estrategia B — Defaults globales + dos archivos contextuales idénticos

**Ventaja:** deja explícito que ambos contextos tienen una presentation config oficial.  
**Problema:** duplica contenido desde el primer día y crea ruido de mantenimiento si siguen idénticos mucho tiempo.

### Estrategia C — Baseline como herencia implícita y validación heredando mágicamente

**Ventaja:** poca duplicación.  
**Problema:** introduce una herencia opaca donde `baseline_current` deja de ser solo un contexto y pasa a ser “el default oculto” del resto. Eso es precisamente el tipo de coupling que conviene evitar.

### Estrategia D — Defaults globales del motor + posibilidad de override por contexto, hoy vacíos o mínimos

**Ventaja:**

- deja clara la arquitectura futura;
- evita duplicación innecesaria;
- no convierte baseline en herencia mágica;
- permite que ambos contextos sigan compartiendo la misma presentación real hoy.

**Problema:** requiere aceptar que al principio habrá poca diferencia visible entre configs.

## 4.3. Recomendación única para el caso real actual

La opción correcta para este repo hoy es la **Estrategia D**:

- un archivo global de defaults de presentación/motor compartido;
- un resolvedor backend que mergee defaults + overrides contextuales;
- carpetas `presentation/` contextuales preparadas;
- y, de momento, `baseline_current` y `validacion_multicontexto` con overrides vacíos o casi vacíos porque su UI actual es idéntica.

## 4.4. Cómo se vería aplicado hoy

### Global

Un default compartido, por ejemplo:

- theme `realistic`;
- mismo `.glb` actual;
- misma cámara/transform;
- misma calibración actual;
- misma motion actual;
- misma voz actual.

### `baseline_current`

Podría tener:

- `presentation/manifest.json` vacío, o solo metadatos/versionado;
- ningún override real.

### `validacion_multicontexto`

Igual que baseline hoy:

- carpeta preparada;
- override vacío o inexistente.

La clave es que **ambos contextos quedan listos para divergir sin sobrediseñar ahora**.

## 4.5. Por qué no usaría baseline como herencia implícita

Porque mezcla dos conceptos distintos:

- baseline como contexto de negocio oficial;
- baseline como default técnico de presentación.

Si mañana cambia el baseline cognitivo o se introduce otro contexto “principal”, esa herencia implícita se vuelve ambigua. Es más limpio tener **defaults globales de runtime/presentation** separados del concepto de contexto baseline.

---

# 5. Veredicto final

## Decisión arquitectónica final

La frontera correcta para este repo es:

### Capa común/global

Debe incluir:

- `index.html` y el shell DOM general;
- overlays, bottom bar, feedback/report UI y flujo hablar/escribir;
- bootstrap frontend/backend y endpoints comunes;
- wiring con STT/TTS;
- API pública del avatar runtime;
- lifecycle, estados y loop del motor.

### Capa específica por contexto

Debe llamarse **`presentation_config`** e incluir:

- `theme` ligero;
- `background`;
- `scene`;
- `avatar.model`;
- `avatar.transform`;
- `avatar.camera`;
- `avatar.calibration`;
- `avatar.motion`;
- `voice`.

### Fuera de esta capa

Deben quedar explícitamente fuera:

- prompts y assets cognitivos;
- persona de negocio/negociación;
- reglas del pipeline;
- evaluación;
- session binding;
- estructura base de la app;
- infraestructura STT/TTS.

## Contrato refinado recomendado

El contrato recomendado para el bootstrap no debería llamarse `ui_context_config`, sino preferiblemente **`presentation_config`**. Un shape razonable para este repo sería:

```json
{
  "version": "1.0",
  "theme": {
    "shell_theme": "realistic",
    "accent": null
  },
  "background": {
    "type": "none",
    "url": null,
    "size": "cover",
    "position": "center center",
    "overlay": {
      "enabled": false,
      "radial_alpha": 0.0,
      "linear_alpha": 0.0
    }
  },
  "scene": {
    "lighting": {
      "key": { "color": "#ffffff", "intensity": 0.9, "position": [2, 4, 3] },
      "rim": { "color": "#ffffff", "intensity": 0.5, "position": [-2, 3, -2] },
      "ambient": { "color": "#ffffff", "intensity": 0.2 }
    }
  },
  "avatar": {
    "model": {
      "url": "/interfaz_usuario/context-assets/default/avatar.glb"
    },
    "transform": {
      "offset": [0, 0, 0],
      "scale": 1.0
    },
    "camera": {
      "fov": 40,
      "near": 0.01,
      "far": 100,
      "position": [0, 0.22, 3.5],
      "target": [0, 0.14, 0],
      "controls_locked": true
    },
    "calibration": {
      "mouth": {},
      "neck": {},
      "eyes": {},
      "mouth_render": {},
      "lipsync": {}
    },
    "motion": {
      "idle": {},
      "micro": {},
      "nod": {},
      "body_bob": {}
    }
  },
  "voice": {
    "voice_id": "alloy",
    "speaking_rate": 1.0,
    "format": "wav"
  }
}
```

## Estructura de archivos recomendada

```text
backend/
  interfaz_usuario/
    presentation_defaults.json          # defaults globales del motor/presentación
    presentation_models.py              # schema tipado opcional
    presentation_resolver.py            # merge defaults + overrides contextuales

  negociacion/
    contexts/
      baseline_current/
        manifest.json
        presentation/
          presentation_config.json      # hoy vacío o mínimo
          assets/
      validacion_multicontexto/
        manifest.json
        presentation/
          presentation_config.json      # hoy vacío o mínimo
          assets/
```

## Cómo crecería con un tercer contexto

Con esta frontera, un tercer contexto solo tendría que:

1. ser resuelto oficialmente por backend como hoy;
2. añadir, si quiere, overrides de `presentation_config` y assets propios;
3. dejar intactos el shell común, el bootstrap común y el runtime común.

## Veredicto final breve

En este repo, la personalización por contexto debe modelarse como **presentación contextual sobre motor común**, no como UI independiente por contexto. La voz encaja en esa presentación; la calibración de boca/cuello/ojos también, pero como subcapa técnica del avatar; y todo lo cognitivo/negocio debe quedar fuera. Para `baseline_current` y `validacion_multicontexto`, hoy conviene mantener la misma presentación efectiva, pero preparar ya la estructura de overrides contextuales apoyada en defaults globales explícitos, no en herencia mágica del baseline.
