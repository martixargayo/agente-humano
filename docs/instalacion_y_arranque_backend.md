# Instalación y arranque del backend

Este documento describe **cómo arrancar este backend en local** y qué depende de instalación/configuración, basado en los archivos reales del repositorio.

---

## 1. Carpeta correcta

El backend debe arrancarse desde la carpeta `backend/`.

Comando correcto (ruta real en este contenedor):

```bash
cd /workspace/agente-humano/backend
```

> Nota de ambigüedad detectada: en instrucciones previas se usó `/workspaces/agente-humano`, pero en este entorno la ruta existente es `/workspace/agente-humano` (sin `s`).

---

## 2. Dependencias del proyecto

### Archivo fuente real de dependencias

La fuente de dependencias Python del backend es:

- `backend/requirements.txt`

En el repo actual se detecta:
- `Procfile` en raíz (arranque Railway),
- `backend/requirements.txt`,
- **no** se detectan `pyproject.toml`, `Pipfile`, `poetry.lock`, `railway.toml` ni `Dockerfile` en los niveles inspeccionados.

### Comando exacto de instalación

Desde raíz del repo:

```bash
python -m pip install -r backend/requirements.txt
```

O desde `backend/`:

```bash
python -m pip install -r requirements.txt
```

### Dependencias Python listadas (obligatorias para arrancar backend)

Según `backend/requirements.txt`:

- `fastapi`
- `uvicorn`
- `pydantic`
- `python-dotenv`
- `typing-extensions`
- `google-auth`
- `google-cloud-speech`
- `python-multipart`
- `openai`
- `openai-agents`

### Notas sobre dependencias opcionales por feature

Aunque Google STT sea opcional a nivel funcional, `backend/api/app.py` importa `google.cloud.speech` en import-time, así que **la librería debe estar instalada** para arrancar el proceso.

Lo opcional en práctica es la **credencial** de Google (`GOOGLE_CREDENTIALS_PATH`), no el paquete.

---

## 3. Variables de entorno mínimas

El backend carga `.env` desde `backend/.env` (`load_dotenv(...)`) y toma plantilla de `backend/.env.example`.

### Obligatorias (mínimas para backend útil)

- `OPENAI_API_KEY`

Sin esta variable, el backend puede arrancar, pero varias rutas IA (chat/negociación/TTS/OpenAI STT fallback) se degradan o responden fallback limitado.

### Opcionales

#### Flags de superficie pública
- `ENABLE_AVATAR_APP` (default código: `1`)
- `ENABLE_OPTIMIZADOR_APP` (default código: `1`)

Para Railway v1 público se recomienda:

```env
ENABLE_AVATAR_APP=0
ENABLE_OPTIMIZADOR_APP=0
```

#### OpenAI speech (opcional, con defaults)
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `OPENAI_TTS_FORMAT`
- `OPENAI_TTS_SPEED`
- `OPENAI_STT_MODEL`

#### Google STT (feature opcional)
- `GOOGLE_CREDENTIALS_PATH`
- `GOOGLE_STT_MODEL`
- `GOOGLE_STT_LANGUAGE`
- `GOOGLE_STT_PUNCTUATION`
- `GOOGLE_STT_ENCODING`

Si falta credencial Google válida, `/stt_google` intenta fallback con OpenAI STT (si hay `OPENAI_API_KEY`).

---

## 4. Comando de arranque local

Comando exacto:

```bash
cd /workspace/agente-humano/backend
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

### Explicación breve

- `api.app:app` -> módulo/objeto ASGI principal en `backend/api/app.py`.
- `--reload` -> autoreload para desarrollo local.
- `--host 0.0.0.0` -> accesible desde fuera del loopback local.
- `--port 8000` -> puerto fijo de dev.

---

## 5. Comando de arranque en Railway

Comando exacto (según `Procfile`):

```bash
cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}
```

### Diferencias frente a local

- Sin `--reload` (producción).
- Puerto dinámico de Railway (`${PORT}`) en vez de `8000` fijo.
- Misma app ASGI (`api.app:app`) y misma carpeta (`backend`).

---

## 6. Comprobaciones rápidas

Una vez arrancado:

1. Salud del backend:

```bash
curl -sS http://localhost:8000/health
```

Esperado: `{"status":"ok"}`.

2. UI pública moderna:

```bash
curl -I http://localhost:8000/interfaz_usuario
```

Esperado: respuesta HTTP 200/304.

3. Turno mínimo API moderna:

```bash
curl -sS -X POST http://localhost:8000/api/interfaz_usuario/negociacion/turn \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u_demo","session_id":"s_demo","message":"hola","new_conversation":false}'
```

Esperado: JSON con campo `reply`.

---

## 7. Problemas típicos

### 1) `ModuleNotFoundError` al arrancar

Causa probable: no se instaló `backend/requirements.txt`.

Acción:

```bash
python -m pip install -r backend/requirements.txt
```

### 2) Error por ruta equivocada al hacer `cd`

Causa probable: usar `/workspaces/...` en vez de `/workspace/...` en este entorno.

Acción: confirmar `pwd` y usar ruta real existente.

### 3) `/stt_google` falla con credenciales Google

Causa probable: `GOOGLE_CREDENTIALS_PATH` ausente o inválido.

Comportamiento esperado: fallback a OpenAI STT si `OPENAI_API_KEY` está configurada.

### 4) Respuestas degradadas o TTS deshabilitado

Causa probable: falta `OPENAI_API_KEY`.

Síntoma: logs de `openai_api_key_missing...`, respuestas fallback o 503 en endpoints de voz.

### 5) `/avatar` o `/optimizador` no disponibles

Causa probable: flags de entorno desactivadas (`ENABLE_AVATAR_APP=0` / `ENABLE_OPTIMIZADOR_APP=0`).

Esto puede ser intencional en Railway v1.

