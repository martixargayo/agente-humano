# RCA runtime flags LLM en `/api/comunicacion` (2026-03-27)

## Resumen corto

Se confirma por código y tests que `disabled_flag` en `contenido`, `delivery` y `global_synthesis` **solo** aparece cuando los gates de env devuelven `False` en runtime. Esos gates leen `os.getenv(...)` en cada evaluación (no hay caché), con parser estricto de booleanos. Si en producción sigue saliendo `disabled_flag` con media real, el problema más probable es de **inyección de env al proceso que realmente atiende** o de **runtime/deploy distinto al esperado**, no de modelos.

## 1) Función exacta que decide `disabled_flag` por rama

- `contenido`: `evaluate_content_from_transcript` llama `_is_content_llm_enabled()` y, si es `False`, fija `llm_mode='fallback'` y `fallback_reason='disabled_flag'` en `runtime_meta`. Fuente: `backend/evaluacion/engine/communication_content_evaluator.py`.
- `delivery`: `evaluate_delivery_with_specialized_from_audio_metrics` llama `_is_audio_llm_enabled()` y, si es `False`, devuelve `runtime_meta={'mode':'fallback','reason':'disabled_flag',...}`. Fuente: `backend/evaluacion/engine/communication_delivery_evaluator.py`.
- `global_synthesis`: `synthesize_global_communication_feedback` evalúa `_is_global_synthesis_llm_enabled()` y, si es `False`, retorna `CommunicationGlobalSynthesisMetaV1(mode='fallback', fallback_reason='disabled_flag')`. Fuente: `backend/evaluacion/engine/communication_synthesis.py`.

## 2) Variable exacta leída por cada rama

- Contenido: `COMM_CONTENT_OPENAI_ENABLED`.
- Delivery: `COMM_AUDIO_OPENAI_ENABLED`.
- Síntesis global: `COMM_SYNTHESIS_OPENAI_ENABLED`.

Todas pasan por `parse_env_bool(name, default=False)` en `backend/evaluacion/engine/communication_llm_config.py`.

## 3) Dónde se lee

En cada evaluación, vía `os.getenv` dentro de:

- `_is_content_llm_enabled()`
- `_is_audio_llm_enabled()`
- `_is_global_synthesis_llm_enabled()`

No hay singleton/cache de flags: cada llamada reevalúa env actual del proceso.

## 4) Truthy/falsy exacto

`parse_env_bool` normaliza con `strip().lower()` y compara:

- truthy: `{"1", "true", "yes", "on"}`
- falsy: `{"0", "false", "no", "off"}`
- cualquier otro valor (incluido vacío/no definido): `default` (aquí siempre `False`)

Implicación: valores como `TRUE ` sí funcionan; valores como `enabled`, `si`, `y`, `t`, `2` NO activan (caen a `False` por default).

## 5) Sitios donde podría sobreescribirse o ignorarse

### 5.1 Overwrite de `.env` local

`backend/api/app.py` ejecuta al importar:

```py
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
```

Si ese `.env` existe y `python-dotenv` usa `override=False` (default), no pisa env ya presentes, pero sí rellena faltantes. Si el proceso productivo no tiene las vars en el entorno real, puede acabar con defaults/falses del `.env` del contenedor.

### 5.2 Rama delivery con placeholder

Aunque el gate esté `True`, si `audio_features` es placeholder, `runtime_meta` se fuerza a `mode='placeholder', reason='audio_features_placeholder'` (no `disabled_flag`). Esto **no** explica tu caso, pero es un override explícito.

### 5.3 Rama visual separada

`visual` no usa las tres flags anteriores. Usa `COMM_VISUAL_MODE` + `COMM_VISUAL_OPENAI_ENABLED`. Ver `backend/evaluacion/engine/communication_evaluators.py` y `communication_visual_config.py`.

## 6) ¿Más de un proceso/servicio implicado?

### En este repo (evidencia directa)

- Comando de arranque esperado: `cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}` en `Procfile` y `nixpacks.toml`.
- No se configuran `--workers` en el comando versionado; por tanto, en el path esperado hay un único proceso Uvicorn (más threads para ramas paralelas).
- Las ramas (`contenido`, `delivery`, `visual`) corren en `ThreadPoolExecutor` dentro del mismo backend/proceso, compartiendo el mismo `os.environ`.

### Riesgo operativo real (fuera del repo)

Sí podría haber más de un **servicio desplegado** en plataforma (otro servicio Railway/proyecto/réplica) apuntando a código/env distintos. El repo no puede descartarlo por sí solo.

## 7) ¿Hay path donde corra código viejo?

En repo, el start oficial es único y apunta a `api.app:app`. No hay otro entrypoint FastAPI alternativo versionado.

Aun así, sí hay riesgo operativo si:

- el deploy activo no usa este commit,
- hay otro servicio detrás del dominio,
- el dominio apunta a entorno distinto del que editaste.

No hay evidencia en código para probar o negar esto sin inspección de plataforma/logs de despliegue.

## 8) Diferencia entre backend real `/api/comunicacion/...` y el configurado

En código, `/api/comunicacion` sale de `comunicacion.api.router` y se monta en `api.app` con `app.include_router(comunicacion_router)`. Por tanto el backend esperado para esa ruta es el mismo proceso que carga env y gates.

Si en runtime ves `disabled_flag` persistente pese a flags ON, la discrepancia más probable es de entorno desplegado (servicio equivocado o vars no inyectadas en ese proceso), no de routing interno.

## 9) Instrumentación mínima recomendada (diagnóstico runtime)

Propuesta segura y mínima:

1. Añadir endpoint interno (por ejemplo `/api/comunicacion/debug/llm-flags`) protegido por `COMM_DEBUG_FLAGS_ENABLED=true`.
2. Devolver solo:
   - flags crudas (normalizadas, sin secretos):
     - `COMM_CONTENT_OPENAI_ENABLED`
     - `COMM_AUDIO_OPENAI_ENABLED`
     - `COMM_SYNTHESIS_OPENAI_ENABLED`
     - `COMM_VISUAL_MODE`
     - `COMM_VISUAL_OPENAI_ENABLED`
   - parse efectivo (`true/false`) usando `parse_env_bool/choice`.
   - `has_openai_api_key` (bool), nunca el valor.
   - huella de build/runtime (`GIT_SHA`, `RAILWAY_SERVICE_NAME`, `RAILWAY_ENVIRONMENT_NAME` si existen).
3. Registrar una línea structured log por evaluación con el snapshot de gating efectivo y `evaluation_id`.

Con eso se distingue inmediatamente:

- flag mal seteada,
- env no inyectada,
- proceso/servicio incorrecto,
- build viejo.

## 10) Pruebas concretas para demostrar lectura real de env

### Pruebas existentes (ya en repo)

- `backend/tests/test_communication_llm_gating_diagnosis.py` ya prueba matrix OFF/ON y razones (`disabled_flag`, `missing_openai_api_key`, `llm`).
- `backend/tests/test_communication_llm_config.py` prueba parseo booleano y choices.

### Prueba operativa recomendada (producción)

1. Activar endpoint de debug propuesto.
2. Hacer request al endpoint y guardar evidencia (timestamp + service metadata).
3. Ejecutar una evaluación real y verificar que `branch_runtime_meta` coincide con snapshot de flags del paso 2.
4. Cambiar una sola flag (ej. `COMM_CONTENT_OPENAI_ENABLED=false`), redeploy, repetir; debe cambiar solo rama contenido a `disabled_flag`.

Si no cambia tras redeploy, evidencia fuerte de deploy no efectivo / servicio equivocado / config source distinto.

## Hipótesis ordenadas por probabilidad

1. **Las env vars no están llegando al proceso que atiende `/api/comunicacion`** (o con valor no parseable por `parse_env_bool`).
2. **Se está llamando a otro servicio/entorno** con defaults (`false/metadata`) aunque tú hayas configurado uno distinto.
3. **Deploy no efectivo / código viejo corriendo** y dominio aún detrás de instancia antigua.
4. **Valor textual inválido en flags** (ej. `enabled` en lugar de `true`/`1`) causando `False` por default.
5. (Menos probable para tu caso) **falta de `OPENAI_API_KEY`**; en ese caso verías `missing_openai_api_key`, no `disabled_flag`.
