# Diagnóstico: por qué el optimizador no está comportándose como banco de pruebas multicontexto

Fecha: 2026-03-30

## Síntomas reportados

1. Al intentar probar `sala-reuniones`, el optimizador parece usar `baseline_current`.
2. Al entrar al optimizador aparece una sesión ya iniciada (de hace horas) en vez de comenzar limpio.
3. Se espera que el optimizador sea el lugar para probar distintos contextos y que al cerrar/abrir se pueda arrancar una conversación nueva.

## Hallazgos técnicos (causa raíz)

### 1) El front del optimizador **reutiliza sesiones previas por diseño** al arrancar

- En `boot()` se llama `refresh({ autoSelect: true })`.
- `refresh()` carga `/sessions` y, si hay sesiones, toma la primera (ordenada por `last_updated` descendente) y la deja activa.
- No existe un paso de “siempre crear sesión nueva al abrir” ni “crear conversación nueva automáticamente al cargar”.

Resultado: si quedó una sesión activa recientemente, vuelves a verla al reabrir la app.

### 2) El botón “Nueva conversación” crea la sesión nueva en backend, pero el front **no cambia la selección** a esa sesión

- `new_conversation_session()` en backend sí crea un `session_id` nuevo (`__newconv__...`) y lo devuelve.
- Pero en el frontend, el handler de `newConvBtn` hace POST y luego `refresh()` sin usar la respuesta para mover `state.selectedSessionKey`.
- Entonces el usuario sigue viendo la sesión anterior, aunque la nueva se haya creado correctamente.

Resultado: parece que “Nueva conversación” no reinicia, cuando realmente el problema es de selección en UI.

### 3) El binding de contexto es por sesión y es estricto (no se puede mutar en caliente una sesión ya ligada a otro contexto)

- `ensure_session_context()` liga el contexto a `world_state["negotiation_context"]` la primera vez.
- Si luego se intenta otro `context_id` en la misma sesión, lanza conflicto `409 session_context_conflict`.

Resultado: para probar otro contexto no sirve “forzar” una sesión existente; hay que abrir una sesión distinta para ese contexto.

### 4) `context_id` y `public_slug` no son lo mismo

- En `sala_reuniones/manifest.json`, `context_id` es `sala_reuniones` (underscore) y `public_slug` es `sala-reuniones` (guion).
- El backend del optimizador resuelve por `context_id`.

Resultado: pedir `sala-reuniones` como `context_id` puede fallar por `unsupported_context_id` (404), y el flujo puede terminar en una sesión ya existente con baseline si la UI no cambió realmente de sesión/contexto.

## Evidencia de validación rápida

- El script de auditoría multicontexto (`backend/scripts/audit_optimizer_multicontext_and_surface_isolation.py`) confirma que:
  - el endpoint `/api/optimizador/contexts` expone `sala_reuniones`,
  - bootstrap con contexto no baseline funciona,
  - el turn del sandbox usa el contexto ligado correctamente.

Es decir: el backend sí soporta multicontexto; el principal desajuste observado está en la UX/estado del frontend de optimizador (reutilización y selección de sesión).

## Conclusión

Lo que estás viendo no es que “el motor no soporte contextos”, sino una combinación de:

1. política de reapertura con sesión previa,
2. falta de switch automático a la sesión recién creada al pedir “Nueva conversación”,
3. confusión entre `sala-reuniones` (slug) y `sala_reuniones` (context_id),
4. restricción correcta de no cambiar contexto dentro de la misma sesión ya ligada.

## Recomendación de implementación (prioridad)

1. **Corregir `newConvBtn` en frontend** para tomar el `session_key` devuelto y asignarlo a `state.selectedSessionKey` antes de `refresh()`.
2. Añadir opción de arranque “sesión limpia” (flag en UI) para no rehidratar automáticamente la última sesión.
3. Permitir que `bootstrap` del optimizador acepte `public_slug` además de `context_id` (o mapear slug→id en frontend) para reducir errores humanos.
4. Mostrar en UI una advertencia explícita cuando se está reabriendo una sesión antigua (edad + contexto) y CTA “Crear conversación nueva y cambiar ahora”.
