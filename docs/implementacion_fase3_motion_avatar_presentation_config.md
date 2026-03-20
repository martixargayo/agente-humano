# Implementación Fase 3 de motion de avatar en `presentation_config`

## Qué se externalizó en Fase 3

En esta fase se sacó de `runtime.js` hacia `presentation_config` la capa de motion expresivo del avatar:

- `avatar.motion.head`
- `avatar.motion.body`
- `avatar.motion.micro`
- `avatar.motion.nod`
- `avatar.motion.body_bob`

## Qué se mantiene igual

- `MotionState` sigue siendo estado interno del motor.
- Los algoritmos de interpolación, micro-motion, nod y body bob siguen siendo los mismos.
- Los contextos con `presentation_config.json` vacío siguen heredando exactamente los defaults globales.

## Archivos tocados

- `backend/interfaz_usuario/presentation_models.py`
- `backend/interfaz_usuario/presentation_defaults.json`
- `backend/interfaz_usuario_app/avatar_runtime/config.js`
- `backend/interfaz_usuario_app/avatar_runtime/runtime.js`

## Compatibilidad

Los overrides parciales siguen funcionando porque el backend hace deep-merge sobre defaults y el runtime normaliza los nombres snake_case del contrato hacia las claves internas en camelCase.
