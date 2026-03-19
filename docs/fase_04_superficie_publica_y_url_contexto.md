# Fase 04 — superficie pública y URL de contexto

## 1. Propósito exacto de la fase

Hacer que la entrada pública pueda seleccionar el contexto correcto por URL o slug, sin romper la superficie existente del baseline.

Va después de la fijación en sesión porque primero hacía falta que backend supiera persistir el contexto resuelto.

---

## 2. Qué se cambia exactamente

Se introduce resolución de contexto en la capa pública de entrada:

- URL/slug -> `context_id`
- bootstrap público -> sesión con `context_id` fijo
- compatibilidad con el acceso actual al baseline

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/api/app.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario_app/app.js`
- `backend/interfaz_usuario_app/index.html` si hace falta un punto de entrada/bootstrapping contextual

### Archivos nuevos posibles

- `backend/negociacion/contexts/public_mapping.py`
- `backend/interfaz_usuario/context_bootstrap.py` si se quiere aislar la traducción slug/contexto

---

## 4. Cambios exactos archivo por archivo

### `backend/api/app.py`

- **Responsabilidad hoy:** montar `/interfaz_usuario` como app estática única.
- **Cambio exacto:**
  - mantener montaje actual intacto para baseline;
  - si se añade nueva superficie pública por slug, hacerlo sin romper `/interfaz_usuario` legacy;
  - cualquier ruta nueva debe resolver al mismo frontend o a un bootstrap contextual compatible.
- **Compatibilidad:** el baseline sigue accesible por la URL actual.

### `backend/interfaz_usuario/__init__.py`

- **Responsabilidad hoy:** exponer bootstrap/new_conversation/turn.
- **Cambio exacto:**
  - ampliar bootstrap para aceptar `context_id` o `public_slug` opcional;
  - opcionalmente añadir un endpoint de resolución de contexto público;
  - mantener `/negociacion/turn` intacto.
- **Compatibilidad:** total para clientes actuales.

### `backend/interfaz_usuario/models.py`

- **Cambio exacto:**
  - añadir `context_id` y/o `public_slug` opcionales a `SessionBootstrapRequest`;
  - no hacer obligatorios esos campos todavía.

### `backend/interfaz_usuario/services.py`

- **Cambio exacto:**
  - traducir `public_slug` a `context_id` vía un resolver backend único;
  - fijar el contexto antes de crear sesión;
  - impedir rebootstrap ambiguo de una sesión existente con otro contexto incompatible.

### `backend/interfaz_usuario_app/app.js`

- **Responsabilidad hoy:** bootstrap manual por `user_id/session_id` sin awareness contextual.
- **Cambio exacto:**
  - leer un slug/contexto desde URL cuando exista;
  - incluirlo solo en bootstrap;
  - seguir usando la sesión ya fijada para el resto de turnos.
- **Compatibilidad:** si no hay slug/contexto, operar igual que hoy con baseline.

### `backend/interfaz_usuario_app/index.html`

- **Cambio exacto:** solo si hace falta exponer metadato de contexto o permitir bootstrap contextual inicial. Evitar rediseños de UI.

### `backend/negociacion/contexts/public_mapping.py`

- **Responsabilidad nueva:** ser la fuente de verdad backend para `public_slug -> context_id`.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  negociacion/
    contexts/
      public_mapping.py
```

Opcionalmente nuevas rutas públicas o bootstrap contextual, pero manteniendo la superficie actual.

---

## 6. Qué NO se toca todavía

- trazas completas;
- evaluación context-aware;
- optimizer context-aware completo;
- prompts/JSON del baseline;
- lógica de `finish_button_armed`;
- shape del estado.

---

## 7. Cómo se garantiza equivalencia funcional

- `/interfaz_usuario` actual sigue funcionando para el baseline;
- si no se aporta slug/contexto, bootstrap resuelve baseline igual que hoy;
- el turn endpoint no cambia su semántica;
- no cambian prompts ni JSON efectivos del baseline;
- no cambia negociación actual;
- no cambia evaluación visible todavía;
- optimizer baseline no depende aún de esta URL pública.

---

## 8. Riesgos específicos de la fase

- frontend resolviendo un contexto y backend otro distinto;
- permitir que una misma sesión cambie de contexto al rebootstrapear desde otra URL;
- introducir demasiada lógica contextual en frontend en vez de centralizar en backend.

---

## 9. Validaciones y checks recomendados

- acceder a la URL actual y comprobar baseline idéntico;
- bootstrap con slug baseline y sin slug, verificar mismo contexto final;
- intentar reusar sesión existente con otro slug y comprobar política conservadora (rechazo o preservación explícita del contexto ya fijado).

---

## 10. Condición de salida

La entrada pública puede resolver y fijar contexto sin romper el acceso actual al baseline.

---

## 11. Rollback / compatibilidad

Mantener la ruta legacy y el bootstrap legacy como camino principal mientras las rutas contextuales nuevas estén en estabilización.
