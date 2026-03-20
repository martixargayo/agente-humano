# Implementación Fase 1 de `presentation_config` en `interfaz_usuario`

## Qué cambié

Se implementó la Fase 1 de `presentation_config` para `interfaz_usuario` con estos cambios efectivos:

- el backend ahora resuelve y devuelve `presentation_config` en `POST /api/interfaz_usuario/sessions/bootstrap`;
- se añadieron defaults globales explícitos en `backend/interfaz_usuario/presentation_defaults.json`;
- se añadió un resolvedor backend para mergear defaults globales + overrides contextuales;
- se añadió una ruta pública para assets contextuales en `/interfaz_usuario/context-assets/{context_id}/{asset_path:path}`;
- el frontend ahora espera el bootstrap backend antes de arrancar el runtime del avatar;
- el runtime ya no se autoarranca al cargar `avatar_runtime/bootstrap.js`;
- el frontend usa `presentation_config.voice.voice_id` y `presentation_config.voice.speaking_rate` al pedir TTS.

## Qué entra en Fase 1

En esta fase se soporta por contexto:

- `theme.shell_theme`
- `background`
- `avatar.model.url`
- `avatar.camera.fov`
- `avatar.camera.near`
- `avatar.camera.far`
- `avatar.camera.position`
- `avatar.camera.target`
- `avatar.transform.offset`
- `avatar.transform.scale`
- `voice.voice_id`
- `voice.speaking_rate`

## Qué queda pendiente para Fase 2

Todavía no se externaliza:

- `avatar.calibration`
- `mouth`
- `neck`
- `eyes/blink`
- `mouth_render`
- `lipsync`
- `avatar.motion`
- lighting contextual más fino

Eso sigue viviendo en el runtime actual y deberá salir a config en la Fase 2.

## Archivos tocados

### Nuevos

- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_resolver.py`
- `backend/negociacion/contexts/baseline_current/presentation/presentation_config.json`
- `backend/negociacion/contexts/baseline_current/presentation/assets/.gitkeep`
- `backend/negociacion/contexts/validacion_multicontexto/presentation/presentation_config.json`
- `backend/negociacion/contexts/validacion_multicontexto/presentation/assets/.gitkeep`

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

## Compatibilidad / límites protegidos

Esta implementación no toca:

- prompts
- orquestación de negociación
- evaluadores
- session binding cognitivo
- reglas de turnos
- flujo de negociación
- lógica de feedback/evaluación

`baseline_current` y `validacion_multicontexto` ya tienen estructura `presentation/`, pero siguen compartiendo la misma presentación efectiva porque ambos usan defaults globales y sus overrides contextuales están vacíos.
