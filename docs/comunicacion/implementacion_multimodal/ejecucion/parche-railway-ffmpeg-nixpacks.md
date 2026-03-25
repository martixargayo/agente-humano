# Parche mínimo Railway: ffmpeg vía Nixpacks

## 1) Problema real detectado
En Railway, el flujo público directo de `comunicacion` seguía degradando a placeholders aunque el `video_ref` ya se persistía como `file://...`.

## 2) Causa raíz
El runtime de Railway no tenía `ffmpeg` disponible. Por eso fallaban:
- extracción de audio,
- extracción de frames,
y el pipeline caía a rutas degradadas antes de análisis multimodal real.

## 3) Decisión técnica tomada
Aplicar un parche mínimo de despliegue sin tocar arquitectura ni pipeline:
- crear `nixpacks.toml` en raíz,
- instalar `ffmpeg` en fase de setup,
- declarar explícitamente el mismo comando de arranque real del proyecto.

## 4) Archivo creado
- `nixpacks.toml`

## 5) Contenido exacto de `nixpacks.toml`

```toml
[phases.setup]
nixPkgs = ["ffmpeg"]

[start]
cmd = "cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}"
```

## 6) Por qué este parche es suficiente y mínimo
- Ataca directamente la causa raíz actual (binario de sistema faltante).
- Mantiene el mecanismo de arranque ya validado (`uvicorn` desde `backend`).
- Evita cambios de arquitectura (sin Dockerfile, sin refactors, sin cambios funcionales).

## 7) Qué NO se ha tocado
- Pipeline multimodal (`backend/evaluacion/*`).
- Bridge/embed/Moodle.
- Contrato `final_result`.
- Frontend público (`backend/comunicacion_app/*`).

## 8) Qué debería desbloquear en Railway tras redeploy
Con `ffmpeg` disponible en runtime, deberían dejar de fallar las etapas que dependen de ese binario para audio y frames, permitiendo que el pipeline use artefactos reales en lugar de caer por ausencia de ffmpeg.

## 9) Limitaciones que siguen existiendo
- Este parche no cambia arquitectura de persistencia ni contratos de report.
- No modifica reglas de fallback por otros errores ajenos a ffmpeg.
- El almacenamiento temporal/local sigue con las mismas características previas del entorno.
