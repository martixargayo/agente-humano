# Ejecución Fase 4 — session_busy embebido

## Qué se cambió

Se implementó el tratamiento explícito de `HTTP 423 session_busy` en el frontend de `interfaz_usuario` para que el simulador embebido no trate ese caso como un error genérico opaco.

### Cambios principales

- Se creó una clase `ApiError` en `backend/interfaz_usuario_app/app.js` para conservar:
  - `status`
  - `errorCode`
  - `retryAfterSeconds`
  - `detail`
- El wrapper `api()` ahora parsea errores JSON, lee `Retry-After` y propaga errores tipados.
- Se añadió estado de UI `sessionBusyState` con cooldown local basado en `Retry-After`, sin reintentos automáticos.
- Se bloquean las acciones interactivas principales mientras la sesión está ocupada:
  - enviar texto
  - finalizar turno
  - cambiar de modo
  - arrancar desde la pantalla de entrada
  - lanzar evaluación/finalización
- Se muestra una UX explícita de sesión ocupada reutilizando superficies existentes:
  - `statusText`
  - `entryError`
  - `feedbackErrorMessage`
  - `meta`
  - `replyContainer`
- Cuando ocurre `session_busy` en contexto embebido, el simulador emite un `postMessage` semántico de tipo `error` al padre con `targetOrigin` fijo `https://academia.gestionce.com`.

## Archivos tocados

- `backend/interfaz_usuario_app/app.js`

## Por qué

La arquitectura de sesión viva ya usa lock distribuido y respuesta fail-fast con `423 session_busy` + `Retry-After`. El frontend necesitaba reflejar esa semántica real para:

- no inventar sesiones nuevas para evitar el lock,
- no reintentar a ciegas,
- mantener UX clara en embebido,
- y notificar al padre Moodle de forma diferenciable.

## Cómo se validó

- `node --check backend/interfaz_usuario_app/app.js`
- `python -m py_compile backend/interfaz_usuario/services.py backend/interfaz_usuario/models.py`
- revisión manual del diff para confirmar que:
  - `postMessage("*")` no aparece,
  - el origin destino es explícito,
  - `Retry-After` se interpreta,
  - y el bloqueo de UI queda acotado a `session_busy`.

## Estado posterior

Los pendientes estrictos de Fase 5 mencionados arriba quedaron resueltos en una iteración posterior del frontend:

- se añadieron mensajes embebidos `final_result_available` y `final_result`,
- el informe final puede serializarse/exportarse a HTML y JSON,
- y existe una exportación PNG basada en rasterización client-side del reporte.

Este documento queda como referencia del cierre específico de `session_busy`; la validación actual del pipeline final debe consultarse en los tests de serving y en la documentación más reciente de la rama.
