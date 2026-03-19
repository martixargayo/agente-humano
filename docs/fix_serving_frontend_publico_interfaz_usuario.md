# Fix mínimo del serving público de `interfaz_usuario`

## Causa raíz

La rotura venía de dos efectos combinados:

1. `index.html` cargaba assets con rutas relativas (`./app.js`, `./feedback_report_view.js`, `./avatar_runtime/bootstrap.js`).
2. `backend/api/app.py` expone rutas dinámicas `/interfaz_usuario/{public_slug}` antes del mount estático `/interfaz_usuario`.

Eso hacía que:

- `/interfaz_usuario/app.js` y `/interfaz_usuario/feedback_report_view.js` pudieran quedar capturados como slug en vez de servirse como ficheros estáticos reales;
- y que la variante `/interfaz_usuario/{public_slug}/` resolviera `./app.js` a `/interfaz_usuario/{public_slug}/app.js`, rompiendo la carga de scripts por nesting del slug.

## Fix elegido

Se aplicó una solución mínima híbrida:

### 1. Paths absolutos estables en `index.html`

Se cambiaron los scripts finales a:

- `/interfaz_usuario/feedback_report_view.js`
- `/interfaz_usuario/avatar_runtime/bootstrap.js`
- `/interfaz_usuario/app.js`

Con esto la variante con slash final deja de romper la resolución de assets por anidamiento de URL.

### 2. Serving explícito de los JS top-level conflictivos en `api/app.py`

Se añadieron rutas explícitas para:

- `/interfaz_usuario/app.js`
- `/interfaz_usuario/feedback_report_view.js`

Con esto esos archivos dejan de depender del mount genérico y ya no pueden quedar capturados por `/interfaz_usuario/{public_slug}`.

## Por qué era el mínimo correcto

- No toca `app.js` más allá de dejar que vuelva a cargar.
- No cambia lógica de bootstrap multicontexto.
- No toca negociación, evaluación, optimizer ni prompts.
- No obliga a rediseñar rutas públicas ni a mover la app a otra URL.
- Resuelve a la vez:
  - la colisión con la ruta dinámica por slug,
  - y la rotura de la variante con slash final.

## URLs soportadas tras el fix

Páginas públicas:

- `/interfaz_usuario`
- `/interfaz_usuario/`
- `/interfaz_usuario/negociacion`
- `/interfaz_usuario/negociacion/`
- `/interfaz_usuario/negociacion-validacion`
- `/interfaz_usuario/negociacion-validacion/`

Assets validados:

- `/interfaz_usuario/app.js`
- `/interfaz_usuario/feedback_report_view.js`
- `/interfaz_usuario/avatar_runtime/bootstrap.js`

## Qué se validó

- que las páginas públicas responden 200;
- que los assets clave responden 200;
- que el HTML ya referencia assets absolutos bajo `/interfaz_usuario/...`;
- que `app.js` servido sigue conteniendo `readPublicSlugFromUrl()` y `bootstrapPayload()`;
- y que la entrada con slash final ya no depende de paths anidados por slug.
