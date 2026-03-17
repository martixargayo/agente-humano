# Checklist operativo — Railway v1 (scope1)

## 0) Alcance

Esta checklist valida solo el scope1:
- arranque Railway,
- superficie pública oficial,
- variables/secretos mínimos,
- documentación de despliegue.

Fuera de scope1: sesiones (`session_id`), feedback runtime, persistencia, Moodle.

---

## 1) Pre-despliegue

- [ ] Start command definido (Procfile o panel Railway).
- [ ] Dependencias instalables desde `backend/requirements.txt`.
- [ ] `OPENAI_API_KEY` cargada en Railway.
- [ ] Flags públicas definidas para Railway (`ENABLE_AVATAR_APP=0`, `ENABLE_OPTIMIZADOR_APP=0`).
- [ ] `.env.example` actualizado con inventario mínimo.
- [ ] Guía de deploy Railway v1 actualizada en `backend/README.md`.

---

## 2) Smoke test tras deploy

- [ ] `GET /health` devuelve 200.
- [ ] `GET /interfaz_usuario` carga correctamente.
- [ ] `POST /api/interfaz_usuario/sessions/bootstrap` responde.
- [ ] `POST /api/interfaz_usuario/negociacion/turn` responde con `reply`.
- [ ] `/avatar` no está montado en Railway (404 esperado con `ENABLE_AVATAR_APP=0`).
- [ ] `/optimizador` no está montado en Railway (404 esperado con `ENABLE_OPTIMIZADOR_APP=0`).

---

## 3) Criterio de “scope1 listo”

Se considera listo cuando:

1. Arranca en Railway y responde por HTTPS.
2. La superficie pública oficial es `/interfaz_usuario` + `/api/interfaz_usuario`.
3. `/avatar` y `/optimizador` quedan fuera del camino público en Railway.
4. Variables mínimas y secretos están definidos/documentados.
5. Existe guía de despliegue ejecutable sin ambigüedad.
