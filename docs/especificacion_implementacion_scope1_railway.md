# Especificación de implementación — Scope 1 Railway v1

## 1. Objetivo y alcance

Definir con precisión **qué se implementará** (y cómo) para habilitar la primera salida a Railway del repositorio, limitando esta fase a cuatro bloques:

- **A. Arranque Railway**
- **B. Superficie pública oficial**
- **C. Variables de entorno y secretos**
- **D. Documentación de despliegue**

Esta especificación **no ejecuta cambios**; describe exactamente qué se tocaría en una implementación posterior.

---

## 2. Decisiones ya fijadas

1. Se desplegará en **una sola instancia Railway**.
2. Superficie pública oficial: **`/interfaz_usuario` + `/api/interfaz_usuario`**.
3. `/avatar` y `/optimizador` deben salir del camino público en Railway.
4. No se tocará en esta fase la política de `session_id`.
5. No se tocará feedback/evaluación en runtime.
6. No se introduce persistencia, Redis, workers ni integración Moodle ahora.
7. Se busca cambio mínimo y robusto para probar v1 en Railway.

---

## 3. Cambios incluidos en esta fase

- Añadir contrato de arranque versionado (recomendación principal: `Procfile`).
- Introducir feature flags para controlar mounts públicos legacy (`/avatar`, `/optimizador`).
- Consolidar inventario de env vars y crear/actualizar `.env.example` operativo para Railway.
- Documentar despliegue paso a paso sin ambigüedades.

---

## 4. Cambios fuera de alcance

## Fuera de alcance de esta implementación

1. Política/estrategia de `session_id` en frontend o backend.
2. Cambios en feedback/evaluación (`/api/interfaz_usuario/feedback/...`).
3. Persistencia en base de datos.
4. Redis, colas o workers separados.
5. Integración con Moodle.
6. Refactor de escenarios o motor conversacional.
7. Endurecimiento integral de concurrencia multi-réplica.

---

## 5. Especificación detallada por bloque

## A. Arranque Railway

### A-01 — Definir método de arranque oficial (bloqueante)

- **ID**: A-01
- **Título**: Contrato de arranque versionado con Procfile
- **Objetivo**: asegurar boot reproducible y explícito en Railway.
- **Bloqueante**: Sí.
- **Archivos a tocar**: `Procfile` (nuevo, raíz repo).
- **Secciones afectadas**: nueva definición `web` process.

**Contenido exacto propuesto (`Procfile`)**

```procfile
web: cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

**Explicación línea por línea**

- `web:` define el proceso HTTP principal para PaaS.
- `cd backend` asegura que imports del paquete backend se resuelven como en desarrollo actual.
- `uvicorn api.app:app` apunta al módulo ASGI real (`backend/api/app.py`, objeto `app`).
- `--host 0.0.0.0` habilita binding externo en contenedor.
- `--port ${PORT}` usa puerto dinámico inyectado por Railway.

**Por qué así y no otra opción**

- **Vs panel-only start command**: Procfile deja contrato en repo (menos deriva entre entornos).
- **Vs `railway.toml`**: válido, pero Procfile es más simple y suficiente para este scope.
- **Vs Dockerfile**: sobrecoste innecesario en esta fase.

**Riesgos**

- Si Railway prioriza otro start command manual, puede ignorar Procfile.
- Si cambian imports relativos del backend, habrá que ajustar el `cd backend`.

**Impacto local**

- Nulo para desarrollo existente; añade alternativa estándar de arranque.

**Impacto Railway**

- Alto positivo: elimina ambigüedad del comando de arranque.

---

### A-02 — Alternativa documentada (no implementada) para panel Railway

- **ID**: A-02
- **Título**: Fallback de arranque desde panel
- **Objetivo**: tener plan B inmediato si Procfile no se usa.
- **Bloqueante**: No (si A-01 ya está aplicado).
- **Archivos a tocar**: documentación (`docs/`), no runtime.

**Comando exacto alternativo**

```bash
cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

---

## B. Superficie pública

### B-01 — Flags para excluir mounts legacy en Railway (bloqueante)

- **ID**: B-01
- **Título**: Feature flags de exposición pública (`/avatar`, `/optimizador`)
- **Objetivo**: retirar rutas legacy del camino público sin romper dev local.
- **Bloqueante**: Sí.
- **Archivo a tocar**: `backend/api/app.py`.
- **Bloques afectados**:
  - mount de `AVATAR_DIR` en `/avatar`
  - mount de `OPTIMIZADOR_DIR` en `/optimizador`

**Flags exactas propuestas**

- `ENABLE_AVATAR_APP` (`"1"` por defecto para no romper local)
- `ENABLE_OPTIMIZADOR_APP` (`"1"` por defecto para no romper local)

**Código/pseudocódigo propuesto**

```python

def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

ENABLE_AVATAR_APP = _env_flag("ENABLE_AVATAR_APP", "1")
ENABLE_OPTIMIZADOR_APP = _env_flag("ENABLE_OPTIMIZADOR_APP", "1")

if ENABLE_AVATAR_APP and AVATAR_DIR.exists():
    app.mount("/avatar", StaticFiles(directory=str(AVATAR_DIR), html=True), name="avatar")

if ENABLE_OPTIMIZADOR_APP and OPTIMIZADOR_DIR.exists():
    app.mount("/optimizador", StaticFiles(directory=str(OPTIMIZADOR_DIR), html=True), name="optimizador")
```

**Comportamiento esperado**

- **Local** (sin env vars): `/avatar` y `/optimizador` siguen activos.
- **Railway** (`ENABLE_AVATAR_APP=0`, `ENABLE_OPTIMIZADOR_APP=0`): no se montan esas rutas.

**Por qué así y no otra forma**

- Evita eliminar código legacy.
- Permite rollback instantáneo por configuración.
- Cambia solo punto de composición de rutas, no motor conversacional.

**Efectos secundarios posibles**

- Cualquier enlace duro a `/avatar` devolverá 404 en Railway (esperado).
- Debe actualizarse documentación para no confundir al equipo.

---

### B-02 — Mantener superficie moderna sin cambios funcionales

- **ID**: B-02
- **Título**: Mantener `/interfaz_usuario` y `/api/interfaz_usuario` como oficiales
- **Objetivo**: no tocar flujos ya válidos de IU moderna.
- **Bloqueante**: Sí (por criterio de producto), pero **sin cambio de runtime** adicional.
- **Archivos a tocar**: docs (alineación de rutas oficiales).

---

## C. Variables de entorno y secretos

### C-01 — Inventario operativo de env vars (bloqueante)

- **ID**: C-01
- **Título**: Clasificación formal de variables para Railway v1
- **Objetivo**: eliminar ambigüedad dev/prod y definir qué se carga en Railway.
- **Bloqueante**: Sí.
- **Archivos a tocar**:
  - `backend/.env.example` (crear o actualizar)
  - docs de despliegue (nueva sección)

#### Clasificación propuesta

### Obligatorias (Railway v1)

1. `OPENAI_API_KEY`
   - **Ejemplo**: `OPENAI_API_KEY=sk-...`
   - **Uso**: cliente OpenAI (chat/negociación/TTS/STT fallback).
   - **Estado**: ya existe en código.
   - **Política**: exigir en Railway, sin fallback operativo real para v1 útil.

### Opcionales (Railway v1)

2. `OPENAI_TTS_MODEL` (default actual `gpt-4o-mini-tts`)
3. `OPENAI_TTS_VOICE` (default actual `cedar`)
4. `OPENAI_TTS_FORMAT` (default actual `wav`)
5. `OPENAI_TTS_SPEED` (default actual `1.10`)
6. `OPENAI_STT_MODEL` (default actual `gpt-4o-mini-transcribe`)
7. `GOOGLE_STT_MODEL`
8. `GOOGLE_STT_LANGUAGE`
9. `GOOGLE_STT_PUNCTUATION`
10. `GOOGLE_STT_ENCODING`

### Solo desarrollo / opcional avanzada

11. `GOOGLE_CREDENTIALS_PATH`
   - En Railway v1, recomendado dejar ausente y usar fallback OpenAI STT.
### Flags de producto (nuevas en esta fase)

11. `ENABLE_AVATAR_APP`
12. `ENABLE_OPTIMIZADOR_APP`

**Propuesta de valores Railway v1**

```env
OPENAI_API_KEY=***
ENABLE_AVATAR_APP=0
ENABLE_OPTIMIZADOR_APP=0
```

---

### C-02 — `.env.example` mínimo propuesto (bloqueante)

- **ID**: C-02
- **Título**: Plantilla de entorno lista para Railway
- **Objetivo**: dar un archivo fuente único para configuración.
- **Bloqueante**: Sí.
- **Archivo a tocar**: `backend/.env.example`.

**Contenido exacto sugerido**

```env
# ===== Core =====
OPENAI_API_KEY=

# ===== Public surface flags =====
ENABLE_AVATAR_APP=1
ENABLE_OPTIMIZADOR_APP=1

# ===== OpenAI speech (optional overrides) =====
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=cedar
OPENAI_TTS_FORMAT=wav
OPENAI_TTS_SPEED=1.10
OPENAI_STT_MODEL=gpt-4o-mini-transcribe

# ===== Google STT (optional) =====
GOOGLE_CREDENTIALS_PATH=
GOOGLE_STT_MODEL=latest_long
GOOGLE_STT_LANGUAGE=es-ES
GOOGLE_STT_PUNCTUATION=true
GOOGLE_STT_ENCODING=WEBM_OPUS
```

**Por qué mantener defaults en código + ejemplo en `.env.example`**

- minimiza cambios runtime,
- mantiene compatibilidad local,
- explicita configuración de producción.

---

## D. Documentación de despliegue

### D-01 — Guía operativa de deploy Railway (bloqueante)

- **ID**: D-01
- **Título**: Instrucciones de despliegue ejecutables
- **Objetivo**: permitir despliegue sin adivinar pasos.
- **Bloqueante**: Sí.
- **Archivos a tocar**:
  - `backend/README.md` (sección “Railway v1”)
  - `docs/checklist_railway_v1.md` (alineación con scope actual)

**Apartados exactos que debe incluir la guía**

1. Pre-requisitos (repo, Railway project, secrets).
2. Método de arranque elegido (Procfile + fallback panel).
3. Variables obligatorias y opcionales.
4. Flags recomendadas para superficie pública (`ENABLE_AVATAR_APP=0`, `ENABLE_OPTIMIZADOR_APP=0`).
5. Smoke tests post-deploy:
   - `GET /health`
   - `GET /interfaz_usuario`
   - `POST /api/interfaz_usuario/negociacion/turn`
6. Límites explícitos v1:
   - estado en RAM,
   - sin garantía de reanudación tras reinicio,
   - single instance.

**Por qué en `backend/README.md`**

- es el punto natural para comandos de backend y despliegue.
- evita dispersar información entre demasiados docs.

---

## 6. Archivos concretos a tocar

### Cambios de implementación (cuando se ejecute)

1. `Procfile` (nuevo)
2. `backend/api/app.py`
3. `backend/.env.example` (nuevo o actualización)
4. `backend/README.md`
5. `docs/checklist_railway_v1.md` (ajuste menor para reflejar scope exacto)

### Documentación de esta especificación (actual fase)

6. `docs/especificacion_implementacion_scope1_railway.md` (este documento)
7. `docs/diff_esperado_scope1_railway.md` (apoyo de cambios esperados)

---

## 7. Código/pseudocódigo propuesto

## 7.1 Procfile

```procfile
web: cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

## 7.2 Flags de exposición pública en `backend/api/app.py`

```python
# helper local en api/app.py

def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

ENABLE_AVATAR_APP = _env_flag("ENABLE_AVATAR_APP", "1")
ENABLE_OPTIMIZADOR_APP = _env_flag("ENABLE_OPTIMIZADOR_APP", "1")

if ENABLE_AVATAR_APP and AVATAR_DIR.exists():
    app.mount("/avatar", StaticFiles(directory=str(AVATAR_DIR), html=True), name="avatar")

if ENABLE_OPTIMIZADOR_APP and OPTIMIZADOR_DIR.exists():
    app.mount("/optimizador", StaticFiles(directory=str(OPTIMIZADOR_DIR), html=True), name="optimizador")
```

## 7.3 `.env.example` mínimo

```env
OPENAI_API_KEY=
ENABLE_AVATAR_APP=1
ENABLE_OPTIMIZADOR_APP=1
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=cedar
OPENAI_TTS_FORMAT=wav
OPENAI_TTS_SPEED=1.10
OPENAI_STT_MODEL=gpt-4o-mini-transcribe
GOOGLE_CREDENTIALS_PATH=
GOOGLE_STT_MODEL=latest_long
GOOGLE_STT_LANGUAGE=es-ES
GOOGLE_STT_PUNCTUATION=true
GOOGLE_STT_ENCODING=WEBM_OPUS
```

---

## 8. Orden exacto de implementación

1. **A-01**: añadir `Procfile`.
2. **B-01**: añadir flags y condicionar mounts legacy en `backend/api/app.py`.
3. **C-02**: crear/actualizar `backend/.env.example` con inventario final.
4. **D-01**: actualizar `backend/README.md` con guía Railway v1.
5. Ajustar `docs/checklist_railway_v1.md` para reflejar alcance exacto de esta fase.
6. Verificación funcional mínima en local y luego en Railway.

---

## 9. Riesgos y efectos secundarios

1. **Riesgo**: 404 en `/avatar` y `/optimizador` en Railway.
   - **Estado**: esperado y deseado para v1 pública.
2. **Riesgo**: confusión entre defaults locales y entorno Railway.
   - **Mitigación**: `.env.example` + README detallado.
3. **Riesgo**: dependencia de OpenAI STT fallback si no se configura Google.
   - **Mitigación**: declararlo explícitamente como simplificación v1.
4. **Riesgo**: no aborda sesiones/feedback/persistencia todavía.
   - **Mitigación**: documentar fuera de alcance.

---

## 10. Criterio de “listo para implementar”

La fase de especificación se considera completa cuando:

1. Existe definición exacta de archivos a tocar y contenido propuesto.
2. Hay comando de arranque Railway concreto y validable.
3. Quedan definidas flags de superficie pública con comportamiento local vs Railway.
4. Existe inventario de env vars clasificado y accionable.
5. Se documentan claramente límites y exclusiones de scope.
6. La tabla de cambios esperados está cerrada para ejecución.

