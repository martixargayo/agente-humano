# Ejecución Fase 04 — superficie pública y URL de contexto

## Qué cambió

Se añadió una resolución pública mínima controlada por backend para traducir `public_slug -> context_id` y usarla en bootstrap sin romper la entrada baseline existente.

## Contrato ampliado

`SessionBootstrapRequest` ahora acepta:

- `context_id` opcional
- `public_slug` opcional

Resolución conservadora:

1. si llega `context_id`, se usa ese contexto;
2. si llega `public_slug`, backend lo traduce a `context_id`;
3. si no llega ninguno, se usa baseline por defecto.

## Resolución `public_slug -> context_id`

La fuente de verdad vive en `backend/negociacion/contexts/public_mapping.py`.

En esta fase solo se soporta el baseline público:

- `public_slug="negociacion"`
- `context_id="baseline_current"`

## Política de conflictos

### Conflicto entre `context_id` y `public_slug` en el mismo bootstrap

Se rechaza explícitamente.

- si el `public_slug` no existe, se devuelve error `unsupported_public_slug`;
- si ambos existen pero resuelven distinto, se devuelve `bootstrap_context_input_conflict`.

### Conflicto con sesión ya fijada

Se mantiene la política de Fase 3: `HTTP 409` con `session_context_conflict`.

## Superficie pública

Se mantiene la entrada actual:

- `/interfaz_usuario`

Y se añade una entrada pública contextual compatible:

- `/interfaz_usuario/{public_slug}`
- `/interfaz_usuario/{public_slug}/`

Ambas sirven el mismo frontend y dejan que el backend resuelva el contexto durante bootstrap.

## Frontend

Cambio mínimo en `app.js`:

- lee el slug desde `window.location.pathname`;
- lo envía solo en bootstrap;
- después reutiliza la sesión ya fijada.

No se añadió selector visual ni rediseño.

## Qué no se tocó todavía

- prompts efectivos
- JSON efectivos
- orden del pipeline
- `finish_button_armed`
- trazas context-aware
- evaluación context-aware
- optimizer context-aware
- segundo contexto oficial

## Por qué sigue siendo compatible con baseline

Porque:

- `/interfaz_usuario` sigue sirviendo la misma app;
- bootstrap sin parámetros sigue resolviendo baseline;
- `public_slug="negociacion"` resuelve al mismo `context_id` baseline actual;
- los turnos posteriores reutilizan la sesión ya fijada.
