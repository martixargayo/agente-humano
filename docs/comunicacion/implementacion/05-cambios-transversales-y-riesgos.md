# 05 — Cambios transversales y riesgos

## 1. Resumen ejecutivo

Este bloque identifica los cambios transversales mínimos necesarios para que `comunicacion` pueda existir como actividad de primera clase sin arrastrar una refactorización grande del repositorio. La idea central es evitar dos errores típicos:

1. **generalizar demasiado pronto** por elegancia;
2. **inyectar lógica de comunicación dentro de negociación** por conveniencia.

El MVP de `comunicacion` solo necesita unos pocos toques transversales; todo lo demás debe quedar encapsulado en módulos nuevos.

---

## 2. Lista exacta de cambios transversales mínimos

| Archivo | Cambio propuesto | Por qué | Riesgo | Prioridad | ¿Puede romper negociación? |
|---|---|---|---|---:|---:|
| `backend/api/app.py` | montar `/comunicacion` y `app.include_router(comunicacion_router)` | exponer nueva surface pública y nueva API | Bajo | Alta | Bajo |
| `backend/sessions/surface_scope.py` | añadir `'comunicacion'` a `SessionSurface` y validaciones | evitar reutilización conflictiva de sesiones | Medio | Alta | Medio |
| `backend/sessions/state.py` | opcional: mejorar neutralidad de `export_session_envelope()` / `hydrate_session_state()` | evitar sesgo hardcoded a negociación si el flujo lo necesita | Medio | Media | Medio |
| `docs/comunicacion/README.md` | enlazar capa de implementación | navegación documental | Nulo | Alta | No |

## 2.1 Cambio más pequeño y seguro por archivo

### `backend/api/app.py`
**Versión mínima**
- definir `COMUNICACION_DIR = BACKEND_DIR / "comunicacion_app"`
- añadir helpers de asset/index equivalentes a los de `INTERFAZ_USUARIO_DIR`
- `app.include_router(comunicacion_router)`
- `app.mount("/comunicacion", StaticFiles(...))`

**Qué NO tocaría**
- no reescribir lógica de `/interfaz_usuario`
- no mezclar rutas de assets de ambos frontends

### `backend/sessions/surface_scope.py`
**Versión mínima**
- ampliar `Literal`
- ampliar set de validación

**Qué NO tocaría**
- no introducir registry dinámica
- no mover esto a config/env

### `backend/sessions/state.py`
**Versión mínima recomendada**
- dejarlo quieto para MVP salvo necesidad real

**Alternativa pequeña si hiciera falta**
- encapsular en helper privado la lectura del bloque de contexto por surface activa
- no rediseñar `SessionEnvelope`

---

## 3. Qué NO tocaría todavía

## 3.1 Piezas que NO conviene generalizar aún
- `backend/evaluacion/contracts/models.py` completo.
- `backend/evaluacion/engine/service.py` como motor multi-dominio genérico.
- `backend/interfaz_usuario_app/app.js` como shell multi-actividad.
- `backend/interfaz_usuario_app/feedback_report_view.js` como renderer universal.
- `backend/negociacion/contexts/*` para “reciclar” resolvers.

## 3.2 Refactors tentadores pero peligrosos
- extraer ya un gran “ActivityFramework” compartido.
- convertir todas las surfaces a una arquitectura plugin.
- rehacer el sistema de sesión para que sea completamente domain-agnostic antes del MVP.
- unificar todos los reports en un solo contrato supergenérico.

## 3.3 Cosas que deben dejarse para después
- storage binario definitivo (si bloquea el primer corte).
- refactor de helpers comunes frontend entre `interfaz_usuario_app` y `comunicacion_app`.
- visual analytics avanzada.
- retry/recovery sofisticado de jobs multimedia.

---

## 4. Riesgos técnicos por prioridad

## 4.1 Altos

### Riesgo A — `SessionSurface` insuficiente
Sin este cambio mínimo, una sesión de `comunicacion` podría colisionar conceptualmente con una de `interfaz_usuario`.

**Mitigación**
- ampliar `SessionSurface` desde el principio.

### Riesgo B — storage binario inexistente
El repo no tiene hoy una abstracción para vídeo/artefactos grandes.

**Mitigación**
- en MVP, permitir refs opacas (`video_ref`, `poster_frame_ref`) sin cerrar aún el backend definitivo de storage.

### Riesgo C — contaminar `negociacion`
Reusar contratos y renderers de negociación por prisa complicaría el mantenimiento.

**Mitigación**
- contratos paralelos nuevos.
- app pública nueva.
- engine paralelo si hace falta.

## 4.2 Medios

### Riesgo D — envelope de sesión sesgado a negociación
`export_session_envelope()` y `hydrate_session_state()` escriben/leen `negotiation_context` y `negotiation_canonical` explícitamente.

**Mitigación**
- posponer generalización salvo necesidad real.

### Riesgo E — permisos cámara/mic en embed
Puede fallar si el iframe no está correctamente configurado.

**Mitigación**
- documentar dependencia de `allow="camera; microphone"` y tests manuales posteriores.

### Riesgo F — payload final con vídeo en Moodle
Queda abierta la forma de exponer `video_ref` de forma segura y reproducible.

**Mitigación**
- usar referencia opaca/firmada más adelante; no fijar ya el mecanismo final si no es necesario para MVP.

## 4.3 Bajos

### Riesgo G — naming inconsistente entre `communication` y `comunicacion`

**Mitigación**
- usar `comunicacion` para rutas/carpeta de dominio del producto.
- reservar `communication_*` solo si se quiere nombrar contratos internos en inglés; recomendación MVP: mantener español coherente.

### Riesgo H — sobreingeniería prematura de artefactos

**Mitigación**
- limitar MVP a transcript + audio features + media block.

---

## 5. Orden de implementación futuro recomendado

1. **surface + router + bootstrap**
   - `backend/comunicacion/api/router.py`
   - mount en `backend/api/app.py`
   - `SessionSurface` mínimo

2. **attempt + upload + storage refs**
   - `AttemptRecord`, `RecordingRecord`
   - create/upload/get attempt

3. **pipeline mínimo de evaluación**
   - transcript
   - audio features básicas
   - bundle consolidado

4. **report básico**
   - assembler nuevo
   - renderer nuevo

5. **UI completa de captura**
   - permissions → preview → recording → review → processing → report

6. **mejoras de artefactos**
   - poster
   - frame set
   - visual summary más rica

7. **integración extendida con Moodle**
   - payload final con vídeo persistente y revisualización completa

---

## 6. Definición del MVP

## 6.1 Qué debe funcionar sí o sí
- bootstrap de sesión `comunicacion`
- create attempt
- attach/upload recording metadata
- submit y creación de `evaluation_id`
- job mínimo que produzca transcript + audio features básicas + report
- UI que muestre vídeo + informe
- embed final con `payloadjson` y referencia de vídeo

## 6.2 Qué queda fuera
- scoring visual fino
- timeline multimodal rica
- comparativa entre intentos
- chunked upload
- persistencia histórica avanzada

## 6.3 Qué se puede mockear temporalmente
- `video_ref` real si el storage final aún no está cerrado
- visual summary / gesture analysis
- algunas métricas de prosodia si la fuente todavía no está lista

### Decisión cerrada de MVP
El MVP debe ser funcionalmente honesto pero técnicamente contenido: una actividad audiovisual con evaluación básica útil. No debe esperar a resolver la analítica visual avanzada para existir.

---

## 7. Recomendación final del bloque

La mejor forma de evitar errores de implementación es imponer disciplina de alcance: tocar solo lo transversal imprescindible, encapsular el resto en módulos nuevos y defender un MVP pequeño pero completo. Si se sigue esta pauta, `comunicacion` podrá nacer rápido sin poner en riesgo la estabilidad del flujo `negociacion`.
