# Diff esperado — Scope 1 Railway v1 (sin ejecutar)

## Tabla de cambios esperados

| Archivo | Acción | Cambio exacto esperado | Motivo | Bloque |
|---|---|---|---|---|
| `Procfile` | Crear | `web: cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}` | Arranque reproducible en Railway | A |
| `backend/api/app.py` | Modificar | Añadir helper `_env_flag(...)`; introducir `ENABLE_AVATAR_APP` y `ENABLE_OPTIMIZADOR_APP`; condicionar mounts de `/avatar` y `/optimizador` | Sacar superficie legacy del camino público en Railway sin romper local | B |
| `backend/.env.example` | Crear/Actualizar | Añadir plantilla con variables core, speech y flags de producto (`ENABLE_AVATAR_APP`, `ENABLE_OPTIMIZADOR_APP`) | Configuración explícita y portable | C |
| `backend/README.md` | Modificar | Nueva sección “Deploy Railway v1”: start method, env vars, smoke checks, límites v1 | Operación sin ambigüedad | D |
| `docs/checklist_railway_v1.md` | Modificar menor | Ajustar checklist para reflejar alcance de scope 1 (arranque/superficie/env/docs) | Alinear checklist con implementación real de esta fase | D |

## No incluido deliberadamente en este diff

- Cambios de política de sesión (`session_id`).
- Cambios de feedback/evaluación.
- Persistencia (DB), Redis, workers.
- Integración Moodle.
- Refactor de dominios o motor conversacional.

