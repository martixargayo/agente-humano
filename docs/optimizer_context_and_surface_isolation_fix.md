# Optimizer: selector real de contexto, alineación de prompts y aislamiento de superficies

## Problema real
Había dos fallos periféricos importantes alrededor del runtime de negociación:

1. El optimizer ya podía ejecutar sandbox con `context_id`, pero la UI no dejaba elegir contexto y el panel de prompts no resolvía el bundle según la sesión activa.
2. Optimizer e `interfaz_usuario` compartían el mismo espacio de sesiones en RAM sin ownership por surface, así que el optimizer podía listar, leer y clonar sesiones ajenas.

## Causa
- La UI del optimizer no cargaba contexts oficiales ni enviaba `context_id` al bootstrap automático.
- `/api/optimizador/prompts` no resolvía prompts desde la sesión/contexto activo.
- El store base seguía siendo `SESSIONS[(user_id, session_id)]` sin guardas periféricas de surface.

## Diseño aplicado
Se aplicó una solución **periférica** para no tocar el core cognitivo:

### 1. Ownership de sesión por surface
Se añadió metadata de ownership de sesión (`optimizador` vs `interfaz_usuario`) y guardas de conflicto por surface.

Esto permite:
- preservar el runtime y el binding de contexto ya existente;
- impedir que ambas superficies reutilicen la misma sesión;
- filtrar listados/lecturas/clones del optimizer para que vea solo sesiones propias.

### 2. Selector real de contexto en optimizer
La UI del optimizer ahora:
- carga contexts oficiales desde `/api/optimizador/contexts`;
- muestra un selector visible;
- crea/abre una sesión optimizer ligada a ese contexto;
- muestra el contexto activo en topbar;
- usa esa sesión en chat/sandbox.

### 3. Panel de prompts alineado con la sesión activa
`/api/optimizador/prompts` ahora puede resolver prompts desde `user_id + session_id` del optimizer.
La UI usa esa ruta context-aware, de modo que el bundle mostrado coincide con el bundle efectivo de runtime.

## Qué NO se tocó
Para proteger el runtime cognitivo, no se tocó:
- `build_negotiation_pipeline_config(...)`
- la lógica de flow de negociación
- el binding de contextos oficiales
- la continuidad conversacional / boundaries / canonical state
- la semántica interna del turno cognitivo

## Endpoints/UI cambiados
- Nuevo endpoint: `GET /api/optimizador/contexts`
- `GET /api/optimizador/prompts` ahora acepta resolución contextual por sesión optimizer
- Guardas de ownership/surface en bootstrap y acceso optimizer/interfaz
- UI del optimizer con selector de contexto, sesión ligada a contexto y etiqueta visible de contexto activo

## Invariantes garantizados ahora
- El optimizer puede elegir un contexto real desde la UI.
- El sandbox/chat del optimizer usa el contexto elegido.
- El panel de prompts muestra el bundle del contexto real activo.
- Optimizer no lista sesiones de `interfaz_usuario`.
- Optimizer no lee turns de `interfaz_usuario`.
- Optimizer no clona sesiones de `interfaz_usuario`.
- El runtime multicontexto existente queda intacto porque la solución se hizo en capas periféricas de surface/session/tooling.
