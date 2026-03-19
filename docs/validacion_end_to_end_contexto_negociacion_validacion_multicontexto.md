# Validación end-to-end real del contexto `validacion_multicontexto`

## Objetivo

Validar con evidencia real si el flow `negociacion` funciona correctamente end-to-end con el contexto oficial alternativo `validacion_multicontexto` (`public_slug=negociacion-validacion`) tras la separación multicontexto.

La pregunta auditada es:

> ¿Está el sistema realmente preparado para funcionar correctamente con la nueva separación de contextos y soportar multicontextualidad sin romper runtime, sesión, trazas, evaluación ni optimizer?

## Contexto probado

- **Contexto prioritario probado:** `validacion_multicontexto`
- **Slug público probado:** `negociacion-validacion`
- **Fallback usado:** no fue necesario.

## Superficie real encontrada

### Entrada pública / frontend

- Ruta pública contextual: `/interfaz_usuario/{public_slug}`.
- Ruta concreta validada: `/interfaz_usuario/negociacion-validacion`.
- El frontend lee el slug desde `window.location.pathname` y, si existe, lo envía como `public_slug` en el bootstrap a `/api/interfaz_usuario/sessions/bootstrap`.

### Backend / APIs efectivas

- Bootstrap de sesión pública: `POST /api/interfaz_usuario/sessions/bootstrap`
- Nuevo hilo conversacional público: `POST /api/interfaz_usuario/negociacion/new_conversation`
- Turno conversacional público: `POST /api/interfaz_usuario/negociacion/turn`
- Evaluación: `POST /api/interfaz_usuario/feedback/evaluations` + `GET /api/interfaz_usuario/feedback/evaluations/{id}` + `GET /api/interfaz_usuario/feedback/evaluations/{id}/report`
- Optimizer bootstrap: `POST /api/optimizador/sessions/bootstrap`
- Optimizer clone sandbox: `POST /api/optimizador/sandbox/clone`
- Optimizer new conversation sandbox: `POST /api/optimizador/sandbox/new_conversation`
- Optimizer sandbox turn: `POST /api/optimizador/sandbox/turn`
- Lectura de trazas optimizer: `GET /api/optimizador/turns/{turn_id}` y `GET /api/optimizador/sessions/{user_id}/{session_id}/turns`

## Enfoque de validación

Se siguió este criterio:

1. **Inspección del código** para confirmar resolución de `public_slug`, binding de sesión, carga de bundles, trazas, evaluación y optimizer.
2. **Ejecución real de la superficie HTTP oficial** con `FastAPI TestClient`.
3. **Mini conversación real reproducible de 3 turnos** sobre el contexto alternativo.
4. **Ejecución real de evaluación y optimizer** sobre esa sesión/contexto.
5. **Comprobación de coexistencia** con `baseline_current`.
6. **Automatización reproducible** en script y test nuevos para no depender solo de lectura manual.

> Nota metodológica: la validación fue end-to-end sobre la integración real del stack, pero con los calls externos al modelo parcheados para hacer la comprobación determinista y no depender de claves/red. No se refactorizó el sistema ni se cambiaron prompts o arquitectura.

## Pasos ejecutados

### 1. Inspección del repo y detección de superficies

Se inspeccionaron:

- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario_app/app.js`
- `backend/negociacion/contexts/*`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/orchestration/turn_contract.py`
- `backend/evaluacion/domains/negotiation/*`
- `backend/negociacion/optimizador/*`

### 2. Ejecución automatizada nueva

Se añadió y ejecutó:

- `backend/scripts/check_e2e_context_validacion_multicontexto.py`

Ese script:

- abre la ruta pública contextual,
- bootstrapea sesión por slug,
- ejecuta 3 turnos por la API pública,
- valida trazas y `_entry_contract.context_meta`,
- fuerza `new_conversation`,
- comprueba conflicto con baseline,
- ejecuta evaluación sobre la sesión real,
- arranca optimizer con ese mismo contexto,
- prueba clone sandbox, new conversation sandbox y sandbox turn,
- lee las trazas del optimizer,
- y comprueba coexistencia con `baseline_current`.

### 3. Cobertura automatizada nueva

Se añadió y ejecutó:

- `backend/tests/test_phase8_second_official_context_e2e_http.py`

Ese test cierra el hueco que quedaba en la cobertura actual: continuidad multi-turn y validación de las rutas HTTP oficiales de interfaz, evaluación y optimizer para el segundo contexto oficial.

## Rutas usadas en la validación

- `GET /interfaz_usuario/negociacion-validacion`
- `POST /api/interfaz_usuario/sessions/bootstrap`
- `POST /api/interfaz_usuario/negociacion/turn`
- `POST /api/interfaz_usuario/negociacion/new_conversation`
- `POST /api/interfaz_usuario/feedback/evaluations`
- `GET /api/interfaz_usuario/feedback/evaluations/{evaluation_id}`
- `GET /api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report`
- `POST /api/optimizador/sessions/bootstrap`
- `POST /api/optimizador/sandbox/clone`
- `POST /api/optimizador/sandbox/new_conversation`
- `POST /api/optimizador/sandbox/turn`
- `GET /api/optimizador/turns/{turn_id}`
- `GET /api/optimizador/sessions/{user_id}/{session_id}/turns`

## Evidencia clave

### A. Descubrimiento de superficie real

- La página pública contextual respondió **200** en `/interfaz_usuario/negociacion-validacion`.
- El frontend sí lee el slug contextual desde URL y lo mete en el bootstrap como `public_slug`.
- El backend resuelve correctamente `public_slug -> context_id` y selecciona `validacion_multicontexto`.

### B. Fijación de contexto en sesión

- El bootstrap por `public_slug=negociacion-validacion` dejó la sesión ligada a:

```json
{
  "flow_id": "negociacion",
  "context_id": "validacion_multicontexto",
  "context_version": "1.0.0"
}
```

- El intento posterior de reusar la misma sesión forzando `baseline_current` devolvió conflicto `409` con:

```json
{
  "error": "session_context_conflict",
  "session_id": "s_ctx",
  "existing_context_id": "validacion_multicontexto",
  "requested_context_id": "baseline_current"
}
```

- `new_conversation` heredó el contexto correcto y no cayó silenciosamente al baseline.

### C. Runtime conversacional

Se ejecutó una mini conversación de **3 turnos** por `POST /api/interfaz_usuario/negociacion/turn`.

Resultados observados:

- `trace_count`: `1 -> 2 -> 3`
- `conversation_id_after`: estable a lo largo de la conversación
- `finish_button_armed`: pasó a `true` en el turno 3
- `entry_contract.entry_surface`: `interfaz_usuario`
- `entry_contract.entrypoint`: `/api/interfaz_usuario/negociacion/turn`

Además, el config efectivo resolvió:

- `prompts_dir = backend/negociacion/contexts/validacion_multicontexto/prompts`
- `persona.json = backend/negociacion/contexts/validacion_multicontexto/assets/persona.json`
- `negotiation_brief.json = backend/negociacion/contexts/validacion_multicontexto/assets/negotiation_brief.json`
- `phase_cards.json = backend/negociacion/contexts/validacion_multicontexto/assets/phase_cards.json`
- `phase_classifier_card.json = backend/negociacion/contexts/validacion_multicontexto/assets/phase_classifier_card.json`

### D. Formación del flujo

La cadena efectiva quedó formada así:

1. **bootstrap** por slug público,
2. **session binding** persistido en `world_state[negotiation_context]`,
3. **pipeline config** resuelto con `context_id=validacion_multicontexto`,
4. **runtime turn contract** aplicado en la superficie pública,
5. **persistencia** de trazas y continuidad conversacional,
6. **new_conversation** con herencia explícita del contexto,
7. **optimizer** montado sobre el mismo `base_context`,
8. **evaluation** resuelta desde el contexto ligado a la sesión.

### E. Trazas y metadata

La última traza pública dejó:

```json
"context_meta": {
  "flow_id": "negociacion",
  "context_id": "validacion_multicontexto",
  "context_version": "1.0.0",
  "official_context_used": true,
  "context_scope": "official"
}
```

Y en `_entry_contract.context_meta` quedó exactamente el mismo contexto, confirmando que el contrato de entrada no pierde el binding contextual.

En optimizer, la traza dejó:

```json
"base_context": {
  "flow_id": "negociacion",
  "context_id": "validacion_multicontexto",
  "context_version": "1.0.0",
  "official_context_used": true,
  "context_scope": "official"
}
```

El `trace_reader` del optimizer también expuso ese `base_context` correctamente.

### F. Evaluación

La evaluación sobre la sesión real del contexto probado devolvió provenance con:

```json
{
  "flow_id": "negociacion",
  "context_id": "validacion_multicontexto",
  "context_version": "1.0.0"
}
```

Además, el script verificó que los assets efectivos de evaluación salían del bundle del contexto alternativo:

- `backend/negociacion/contexts/validacion_multicontexto/evaluation/core_evaluator_prompt.txt`
- `backend/negociacion/contexts/validacion_multicontexto/evaluation/trajectory_evaluator_prompt.txt`
- `backend/negociacion/contexts/validacion_multicontexto/evaluation/rubric.json`

### G. Optimizer

Se validó lo siguiente con ejecución real de endpoints:

- bootstrap optimizer con `context_id=validacion_multicontexto`,
- clone sandbox heredando ese mismo contexto,
- new conversation sandbox heredando ese mismo contexto,
- sandbox turn usando ese contexto como base real,
- visibilidad del contexto en la lectura de trazas.

No se observó borrado del `base_context` por encima de los metadatos del optimizer.

### H. Coexistencia con baseline

Se bootstrapeó en paralelo también `baseline_current` por `public_slug=negociacion`.

Resultado:

- baseline quedó ligado a `context_id=baseline_current`,
- el contexto alternativo quedó ligado a `context_id=validacion_multicontexto`,
- ambos comparten `flow_id=negociacion`,
- ambos resuelven `prompts_dir` distintos,
- no se pisan entre sí ni hubo caída silenciosa del contexto alternativo al baseline.

## Qué funcionó

- La **ruta pública contextual** existe y responde.
- El **frontend** manda el `public_slug` correcto al bootstrap.
- El backend resuelve bien **`public_slug -> context_id`**.
- La **sesión queda fijada** al contexto correcto y lo persiste.
- La política de **conflicto de contexto** rechaza mezclas incompatibles.
- El **runtime** usa el `prompts_dir` y los assets del contexto alternativo.
- La conversación mantiene **continuidad multi-turn** sin mezclarse con baseline.
- Las **trazas** salen con `context_meta` correcto.
- `_entry_contract.context_meta` conserva el contexto correcto.
- La **evaluación** toma el contexto correcto y deja provenance correcta.
- El **optimizer** usa `validacion_multicontexto` como `base_context` real.
- `baseline_current` y `validacion_multicontexto` **coexisten** sin romperse.

## Qué no funcionó

No aparecieron fallos bloqueantes ni importantes en la validación ejecutada.

Sí apareció una observación operativa normal de la API de evaluación:

- justo después de crear una evaluación, el primer `GET .../report` puede responder `409 evaluation_not_completed:queued` antes de que el worker termine;
- tras un breve polling, el informe queda disponible con `200`.

Esto **no se clasificó como bug**, porque el comportamiento es coherente con una evaluación asíncrona.

## Bugs encontrados

### Ningún bug bloqueante detectado en esta validación

No fue necesario usar el fallback `baseline_current` como contexto principal.

### Hallazgo menor / diagnóstico

- **Tipo:** MENOR
- **Síntoma:** el informe de evaluación no siempre está disponible inmediatamente tras `POST /feedback/evaluations`.
- **Reproducción:** pedir el report justo después del create.
- **Causa:** pipeline asíncrona; el job todavía puede seguir en `queued`.
- **Impacto:** exige polling del estado/report y hay que documentarlo como parte del contrato de integración.
- **Corrección aplicada:** no; no es un bug del sistema multicontexto, sino una característica observable del flujo asíncrono.

## Fixes aplicados

No se aplicaron fixes funcionales al sistema de negocio.

Solo se añadieron entregables de validación:

- `backend/scripts/check_e2e_context_validacion_multicontexto.py`
- `backend/tests/test_phase8_second_official_context_e2e_http.py`
- este documento

## Respuesta a los criterios de aceptación

1. **¿Existe una forma real de abrir/jugar el contexto probado?** Sí.
2. **¿La sesión queda fijada al contexto correcto?** Sí.
3. **¿El runtime usa prompts y assets del contexto correcto?** Sí.
4. **¿Se generan trazas con el contexto correcto?** Sí.
5. **¿La evaluación usa el contexto correcto?** Sí.
6. **¿El optimizer usa ese contexto como base real?** Sí.
7. **¿Baseline y segundo contexto coexisten sin mezclarse?** Sí.
8. **¿Hay caída silenciosa a baseline?** No se observó.
9. **¿Hay zonas donde la separación sea solo aparente?** No en la cadena auditada.
10. **¿Está listo el sistema para esta separación multicontexto?** Sí, en la cadena validada.

## Conclusión final honesta

**Veredicto: sí, el sistema está bien formado para multicontextualidad en la cadena auditada.**

Con la evidencia reunida, el contexto oficial `validacion_multicontexto`:

- puede abrirse por superficie pública real,
- fija sesión correctamente,
- ejecuta runtime conversacional con el bundle correcto,
- deja trazas y metadata coherentes,
- alimenta evaluación con el contexto correcto,
- y funciona como `base_context` real del optimizer,
- mientras `baseline_current` sigue coexistiendo sin interferencia.

La única cautela operativa observada es la ya esperable naturaleza asíncrona de la evaluación, que obliga a polling antes de pedir el informe.
