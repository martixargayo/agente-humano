# Implementación Fase 2 de calibración de avatar en `presentation_config`

## Qué se externalizó en Fase 2

En esta fase se sacó de `runtime.js` hacia `presentation_config` únicamente la calibración técnica dependiente del mesh:

- `avatar.calibration.mouth`
- `avatar.calibration.neck`
- `avatar.calibration.eyes`
- `avatar.calibration.mouth_render`
- `avatar.calibration.lipsync`

Los algoritmos de blink, mouth render y lipsync siguen siendo los mismos; solo cambió la procedencia de los valores.

## Qué sigue aún fuera de config

Sigue fuera de `presentation_config` en esta fase:

- `avatar.motion`
- refinamientos de `scene`/lighting contextual
- cambios adicionales de `voice`
- layout/HTML
- lógica cognitiva y flujo de negociación

## Archivos tocados

- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario_app/avatar_runtime/config.js`
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

## Qué queda para Fase 3

La Fase 3 debería cubrir únicamente:

- `avatar.motion`
- refinamientos contextuales de escena que sí pertenezcan a presentación
- cualquier ajuste mínimo adicional de presentación que no sea calibración técnica del mesh
