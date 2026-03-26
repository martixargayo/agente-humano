# 08 · Aislamiento de sesiones y concurrencia multiusuario

## 1) Objetivo del doc
Evaluar si `comunicacion` está aislada por sesión/attempt/user para uso concurrente (dos usuarios/equipos en paralelo), comparar con negociación e identificar riesgos reales sin implementar cambios.

## 2) Archivos/pantallas inspeccionados
- `backend/comunicacion/api/router.py`
- `backend/comunicacion/services/session_service.py`
- `backend/comunicacion/services/attempt_service.py`
- `backend/comunicacion/services/recording_service.py`
- `backend/comunicacion/services/evaluation_service.py`
- `backend/comunicacion/storage/repository.py`
- `backend/comunicacion/storage/models.py`
- `backend/evaluacion/engine/communication_service.py`
- `backend/sessions/state.py`
- `backend/sessions/redis_store.py`
- `backend/sessions/session_lock.py`
- `backend/interfaz_usuario/services.py` (comparativa)

## 3) Evidencia exacta encontrada en repo

### 3.1 IDs y ownership (fortaleza)
- `attempt_id`, `recording_id`, `evaluation_id` se generan con prefijos (`att_`, `rec_`, `eval_`).
- Operaciones sensibles validan ownership por `user_id` + `session_id`:
  - `_assert_attempt_ownership()` en attempt/recording/evaluation creation.
- `create_communication_evaluation()` exige que el attempt pertenezca al `user_id/session_id` recibido.

### 3.2 Sesión y contexto (fortaleza)
- `ensure_communication_session()` crea/rehidrata sesión con `user_id/session_id` y enlaza contexto.
- Runtime refs de comunicación (`active_attempt_id`, `last_recording_id`, `latest_evaluation_id`) se guardan en `state.world_state.communication_runtime`.

### 3.3 Repositorios in-memory (punto delicado)
- `comunicacion.storage.REPOSITORY` es `InMemoryCommunicationRepository` global de proceso.
- Jobs/report de comunicación en evaluación también se guardan en bloques in-memory adjuntos a ese repositorio.
- Hay lock de thread en repositorio (seguridad intra-proceso), pero no persistencia distribuida para estos bloques.

### 3.4 Diferencia clave con negociación
- Negociación/interfaz_usuario usa `acquire_session_execution_lock()` en rutas críticas (`run_turn`, `finalize_session`), devolviendo 423 `session_busy` cuando hay concurrencia sobre misma sesión.
- En comunicación no se encontró uso equivalente de `acquire_session_execution_lock` en create/upload/submit.

### 3.5 Session store base
- `sessions.state` soporta memory o Redis para estado de sesión.
- Pero artefactos de comunicación/evaluación siguen in-memory en el repositorio específico (no Redis-native en este módulo).

## 4) Diagnóstico del estado actual

### 4.1 Concurrencia básica multiusuario (usuario A vs usuario B)
- **Generalmente segura** en términos de aislamiento lógico por IDs y ownership.
- Dos usuarios distintos no deberían pisarse si cada uno opera con su `user_id/session_id` correcto.

### 4.2 Concurrencia sobre misma sesión (mismo user/session en paralelo)
- Riesgo mayor que negociación por ausencia de lock de ejecución por sesión en endpoints de comunicación.
- Posibles carreras:
  - doble submit de attempt,
  - writes solapados de estado/refs,
  - actualización de status de attempt en orden no esperado.

### 4.3 Escalado multi-proceso
- Riesgo de inconsistencia si hay varios workers y repositorios in-memory no compartidos.
- Persistencia de jobs/reports atada al proceso que los creó.

## 5) Referencia visual/técnica exacta encontrada en negociación/comunicación
- Negociación: lock explícito + error semántico `session_busy` + retry-after.
- Comunicación: ownership checks correctos, pero sin lock equivalente y con más estado efímero in-memory en evaluación.

## 6) Propuesta detallada de mejora futura (sin implementar)
1. Adoptar bloqueo por sesión en endpoints críticos de comunicación:
   - create/upload/submit/report fetch (al menos submit/evaluation trigger).
2. Definir política idempotente para `submit`.
3. Mover/respaldar estado de jobs/report a storage compartido si hay despliegue multi-worker.
4. Mantener ownership checks actuales (son correctos y deben conservarse).

## 7) Layout detallado (mapa de aislamiento)
- Capa sesión: `user_id + session_id`.
- Capa intento: `attempt_id` ligado a owner.
- Capa media: `recording_id` ligado a attempt/owner.
- Capa evaluación: `evaluation_id` ligado a attempt.
- Capa runtime UI: refs en `world_state.communication_runtime`.

## 8) Tabla de reutilización

| Pieza actual | Archivo origen | Reutilizar / adaptar / descartar | Motivo | Destino futuro |
|---|---|---|---|---|
| `_assert_attempt_ownership` | `backend/comunicacion/services/attempt_service.py` | Reutilizar tal cual | control de acceso correcto | mantener en todo flujo |
| `write_communication_runtime_refs` | `backend/comunicacion/services/session_service.py` | Reutilizar | trazabilidad de refs útil | conservar |
| `InMemoryCommunicationRepository` | `backend/comunicacion/storage/repository.py` | Adaptar en futuro | lock thread sí, pero no distribuido | backend persistente/compartido |
| `_jobs_block/_reports_block` | `backend/evaluacion/engine/communication_service.py` | Adaptar | estado efímero por proceso | storage durable |
| `acquire_session_execution_lock` patrón | `backend/sessions/session_lock.py` + `backend/interfaz_usuario/services.py` | Adaptar a comunicación | probado en negociación | hardening concurrencia |

## 9) Tabla de implementación futura por archivo

| Archivo | Qué parte exacta tocar | Qué conservar | Qué eliminar | Qué añadir | Riesgo |
|---|---|---|---|---|---|
| `backend/comunicacion/services/*.py` | rutas críticas create/upload/submit | checks de ownership | operaciones sin lock | session lock + manejo 423 | Medio/Alto |
| `backend/evaluacion/engine/communication_service.py` | gestión de jobs/report | pipeline de evaluación | dependencia fuerte de diccionarios in-memory | persistencia compartida | Alto |
| `backend/comunicacion/storage/repository.py` | repositorio base | contratos de modelos | limitación in-memory puro | backend durable opcional | Alto |
| `backend/comunicacion/api/router.py` | contratos HTTP | shape de payloads | exposición no autenticada de status/report (si aplica) | validaciones adicionales opcionales | Medio |

## 10) Riesgos o puntos delicados
- Cambiar storage/locking impacta contratos operativos y despliegue.
- Si no se aborda, en carga real pueden aparecer comportamientos no deterministas por proceso.
- Endpoint de status/report por `evaluation_id` sin ownership explícito requiere revisión de seguridad según contexto de autenticación global.

## 11) Criterio de aceptación visual/UX
(para la fase técnica posterior)
- Dos usuarios distintos pueden operar en paralelo sin contaminación de resultados.
- Misma sesión concurrente no produce corrupción de estado; retorna busy/idempotencia controlada.
- Report y status son consistentes aunque haya más de un worker.
