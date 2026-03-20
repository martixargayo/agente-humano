# Mapa de cambios del repo para Redis sessions

## Criterio

Este mapa distingue entre:
- **imprescindible ahora**: necesario para tu objetivo real;
- **recomendable después**: endurecimiento útil pero no bloqueante;
- **aplazable**: fuera del objetivo mínimo.

## Tabla principal

| Archivo / zona | Por qué tocarlo | Qué cambiar | Tamaño | Riesgo | Dependencias | Prioridad |
|---|---|---|---|---|---|---|
| `backend/interfaz_usuario/models.py` | Hoy define IDs públicas compartidas por defecto | Eliminar defaults, permitir bootstrap server-side | Pequeño | Bajo | router bootstrap | Imprescindible ahora |
| `backend/interfaz_usuario/__init__.py` | Expone bootstrap y turn endpoint público | Ajustar contrato de bootstrap para IDs emitidas por backend | Pequeño | Bajo | services | Imprescindible ahora |
| `backend/interfaz_usuario/services.py` | Carga sesión, crea conversaciones nuevas y ejecuta turnos | Migrar a `SessionStore`, meter lock por sesión, renovar TTL | Medio | Alto | store, Redis, OpenAI continuity | Imprescindible ahora |
| `backend/interfaz_usuario_app/index.html` | Hoy renderiza defaults compartidos visibles | Quitar inputs por defecto o volverlos solo debug | Pequeño | Bajo | app.js | Imprescindible ahora |
| `backend/interfaz_usuario_app/app.js` | Hoy reutiliza IDs del DOM | Consumir bootstrap server-side, persistir IDs únicas en cliente | Medio | Medio | bootstrap backend | Imprescindible ahora |
| `backend/sessions/state.py` | Hoy concentra `SESSIONS` en RAM y helpers globales | Introducir abstracción `SessionStore`; dejar in-memory solo para local/test | Grande | Alto | muchos call-sites | Imprescindible ahora |
| `backend/negociacion/orchestration/flow_config.py` | Guarda/lee canonical, recent_dialogue y traces desde `SessionState` | Mantener lógica, pero asumir `SessionState` rehidratado desde store; quizá versionar snapshot | Medio | Alto | SessionStore, snapshot schema | Imprescindible ahora |
| `backend/negociacion/state/canonical_state.py` | Define el bloque operativo real | No reescribir lógica; sí fijar qué campos serializan y cómo migran | Medio | Alto | snapshot versioning | Imprescindible ahora |
| `backend/negociacion/contexts/session_binding.py` | Binding de contexto crítico para aislamiento | Mantener; asegurar que el binding persiste en Redis | Pequeño | Medio | SessionStore | Imprescindible ahora |
| `backend/sessions/surface_scope.py` | Binding de superficie crítico para aislamiento | Mantener; asegurar persistencia en Redis | Pequeño | Medio | SessionStore | Imprescindible ahora |
| `backend/api/app.py` | Wiring global del backend | Inicializar store Redis, healthcheck, config vía env | Medio | Medio | Redis URL | Imprescindible ahora |
| `backend/negociacion/orchestration/turn_contract.py` | Punto estable alrededor del turno | Opcionalmente envolver lock/metadata aquí o en services | Pequeño | Medio | services | Recomendable |
| `backend/evaluacion/engine/service.py` | Lee sesión actual para construir bundle | Adaptar a `SessionStore` si feedback sigue leyendo sesiones vivas | Medio | Medio | SessionStore | Recomendable después |
| `backend/evaluacion/storage/in_memory_repository.py` | Sigue siendo in-memory | Solo tocar si evaluación debe sobrevivir a réplica/restart | Medio | Medio | alcance producto | Aplazable |
| `backend/negociacion/optimizador/experiments_bridge.py` | Overrides en RAM | No imprescindible para tu objetivo público mínimo; documentar que sigue no replica-safe | Medio | Medio | optimizer UI | Aplazable |
| `backend/negociacion/optimizador/session_bridge.py` | Lista/clona sesiones desde RAM | Adaptar después si optimizer va a usarse en Railway multiusuario real | Medio | Medio | SessionStore | Aplazable |
| `backend/tests/*` | Deben cubrir contaminación y continuidad | Añadir tests de Redis, locks, TTL y réplica-like | Medio | Bajo | test infra | Imprescindible ahora |

## Qué piezas deberían mantenerse igual

1. prompts;
2. planner/executor/phase classifier;
3. modelos de dominio del canónico;
4. resolución de contextos oficiales;
5. trazas y contratos de entrada.

## Qué piezas deberían abstraerse

1. `SESSIONS` → `SessionStore`.
2. locking por sesión → `SessionLockManager` o helper Redis.
3. bootstrap de identidad → servicio único de creación de sesión.
4. serialización del snapshot → módulo dedicado, no lógica dispersa.

## Qué piezas deberían dejar de depender de RAM local

### Sí o sí
- sesión viva pública,
- continuity OpenAI,
- recent dialogue,
- canonical state,
- context/surface binding.

### No necesariamente en esta fase
- artifacts largos,
- dataset histórico,
- reports internos permanentes,
- optimizer completo.

## Dónde introducir el lock por sesión

### Punto recomendado
`backend/interfaz_usuario/services.py`, justo al inicio del flujo que procesa `run_turn`.

### Por qué ahí
- ya conoce `user_id`, `session_id`, `context_id` y `surface`;
- es el entrypoint público crítico;
- evita contaminar capas muy internas con detalles infra antes de tiempo.

## Dónde gestionar `conversation_id` o `previous_response_id`

### Punto recomendado
Seguir usando el modelo actual `openai_thread` dentro del canónico, pero persistido dentro del snapshot Redis.

### Por qué
- minimiza cambios en el pipeline;
- conserva compatibilidad con la lógica actual;
- no rompe trazas ni contratos.

## Componentes de optimizer/evaluación a tocar mínimamente

### Optimizer
No es imprescindible para el objetivo mínimo de la interfaz pública. Lo mínimo responsable es:
- documentar que sigue no replica-safe,
- evitar que comparta rutas críticas con producción pública si no se migra aún.

### Evaluación
Si se usa solo al final y no requiere larga duración, basta con:
- leer la sesión desde el nuevo `SessionStore`;
- aceptar que el repositorio de reports siga simple por ahora, salvo que polling multi-réplica también sea requisito inmediato.

## Esqueleto propuesto

### `SessionStore`
- `get(session_key) -> SessionEnvelope | None`
- `save(session_key, envelope, ttl_seconds)`
- `delete(session_key)`
- `touch(session_key, ttl_seconds)`
- `create(initial_envelope, ttl_seconds)`

### `SessionEnvelope`
- `schema_version`
- `user_id`
- `session_id`
- `context_binding`
- `surface_binding`
- `canonical_state`
- `recent_dialogue`
- `traces_meta` o `traces`
- `created_at`
- `updated_at`
- `last_turn_id`

### Claves Redis sugeridas
- `session:{session_id}`
- `lock:session:{session_id}`
- opcional: `user_sessions:{user_id}` si luego necesitas listar activas

## Checklist de rollout

1. quitar defaults compartidos;
2. meter bootstrap server-side;
3. introducir `SessionStore` con implementación memory;
4. añadir Redis detrás de feature flag;
5. mover superficie pública a Redis;
6. añadir lock por sesión;
7. activar TTL;
8. correr tests de réplica-like y restart;
9. desplegar staging con healthcheck;
10. observar drift de negociación y colisiones.
