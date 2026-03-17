# Auditoría de contraste (Railway + Moodle + multiusuario)

> Base de contraste: `docs/auditoria_tecnica_railway_moodle.md`.
> 
> Esta versión **revalida en código** cada punto y distingue:
> - **[HECHO]** observado en el repo.
> - **[INFERENCIA]** deducción razonable.
> - **[OPCIÓN ALTERNATIVA]** solución distinta pero válida.

## A. Veredicto general

- **Conclusión corta**: el repo está **más cerca de una v1 Railway** de lo que parecía, pero **más lejos de multi-réplica + Moodle robusto** de lo que necesitará en fase 2.
- **Comparado con la auditoría anterior**:
  - **Mejor de lo que parecía** en: separación de superficie moderna (`/api/interfaz_usuario`), contratos de entrada por turno, trazabilidad, configuración modular de pipelines y degradación controlada sin ciertas dependencias.
  - **Igual o peor** en: persistencia durable (sesiones y feedback siguen en RAM), aislamiento concurrente fuerte por sesión, y preparación explícita para múltiples réplicas.

## B. Matriz de contraste requisito por requisito

| Requisito | Estado actual | Evidencia en código | Riesgo real | Urgencia | Alternativas válidas |
|---|---|---|---|---|---|
| Servicio web desplegable (FastAPI) | **Resuelto** | `app = FastAPI(...)` y rutas montadas en `backend/api/app.py`. [HECHO] | Bajo | Alta (ya usable) | Ninguna necesaria para v1 |
| Host/Port Railway (`0.0.0.0:$PORT`) | **Parcial** | No hay script de arranque versionado ni lectura explícita de `PORT` en repo; sí existe app ASGI importable. [HECHO] | Medio (operativo) | Bloqueante práctico de despliegue si no se define en Railway | [OPCIÓN ALTERNATIVA] Configurar start command en Railway (`uvicorn api.app:app --host 0.0.0.0 --port $PORT`) sin tocar código |
| Variables de entorno limpias | **Parcial** | Usa `load_dotenv(...)`, `OPENAI_*`, `GOOGLE_*`, `ENABLE_FEEDBACK_DEV_FIXTURES`; fallback local para credencial Google. [HECHO] | Medio | Alta | [OPCIÓN ALTERNATIVA] Mantener `.env` local para dev y setear vars en Railway; no obliga a refactor inmediato |
| Dependencias frágiles de localhost/rutas locales | **Parcial** | `GOOGLE_CREDENTIALS_PATH` default a ruta local de workspace. [HECHO] | Medio | Alta | [OPCIÓN ALTERNATIVA] Desactivar Google STT en cloud y usar fallback OpenAI STT inicialmente |
| Secretos | **Parcial** | API key por env; no hardcoded keys en código auditado. [HECHO] | Bajo-medio | Alta | [OPCIÓN ALTERNATIVA] solo `OPENAI_API_KEY` en v1 y postergar Google credentials |
| Frontend embebido + static assets | **Resuelto (otra forma válida)** | `app.mount('/avatar'...)`, `app.mount('/interfaz_usuario'...)`. [HECHO] | Bajo | Media | [OPCIÓN ALTERNATIVA] servir frontend por CDN más adelante; no bloquea v1 |
| Compatibilidad instancia única inicial | **Resuelto** | Estado por `(user_id, session_id)` en diccionario global; feedback también en mismo proceso. [HECHO] | Medio (reinicio pierde estado) | Alta | [OPCIÓN ALTERNATIVA] Single replica + sesiones cortas + aviso de no reanudación histórica |
| Compatibilidad futuras réplicas | **No resuelto** | `SESSIONS` y feedback repo son en RAM de proceso. [HECHO] | Alto | Fase 2 (antes de escalar) | [OPCIÓN ALTERNATIVA] sticky sessions temporalmente, con límites claros |
| Estado conversacional persistente durable | **No resuelto** | `SESSIONS: Dict[...] = {}` y `save_session_state` en RAM. [HECHO] | Alto (pérdida en restart) | Muy alta | [OPCIÓN ALTERNATIVA] persistencia mínima solo de sesión activa+turnos (Postgres) |
| Persistencia feedback/evaluación | **No resuelto** | `InMemoryFeedbackRepository` + `_jobs/_reports` en memoria. [HECHO] | Alto para auditoría/reportes | Alta si feedback es funcionalidad crítica | [OPCIÓN ALTERNATIVA] desactivar feedback en v1 pública |
| Aislamiento por usuario/sesión | **Parcial (útil)** | Clave `(user_id, session_id)`, endpoints modernos exigen ambos campos. [HECHO] | Medio (colisiones si IDs mal gestionados por cliente) | Alta | [OPCIÓN ALTERNATIVA] imponer generación server-side de `session_id` para interfaz productiva |
| Riesgo de mezcla en superficie legacy | **No resuelto en legacy** | `avatar_app/app.js` usa `user_id: 'web_user', session_id: 'sesion_demo'`. [HECHO] | Alto si se usa esa UI en producción | Muy alta | [OPCIÓN ALTERNATIVA] usar solo `/interfaz_usuario` en v1 y dejar `/avatar` como demo interna |
| Controles de concurrencia/locks | **Parcial** | Lock en repo feedback y locks puntuales (`SummarizingSession`), pero no lock transaccional por sesión global. [HECHO] | Medio-alto con requests simultáneas misma sesión | Alta | [OPCIÓN ALTERNATIVA] serialización por cliente (una petición/turno) en v1 |
| Jobs de fondo | **Resuelto (forma simple)** | `ThreadPoolExecutor(max_workers=4)` en proceso web. [HECHO] | Medio (contención CPU y no durable) | Media | [OPCIÓN ALTERNATIVA] mantener en-proceso en piloto pequeño |
| Base para Moodle (IDs y contrato de entrada) | **Parcial fuerte** | Requests incluyen `user_id/session_id`; `entry_contract` y `config_snapshot` se trazan por turno. [HECHO] | Bajo para arranque; medio para evaluación formal | Alta | [OPCIÓN ALTERNATIVA] mapear `user_id=session_user`, `session_id=attempt_id` inicialmente |
| Soporte de múltiples escenarios | **Parcial** | separación `chat/negociacion`, `flow_config`, prompts y schemas por dominio; pero negociación tiene fases/rúbricas hardcoded. [HECHO] | Medio | Media-alta | [OPCIÓN ALTERNATIVA] introducir `scenario_id` en capa API y resolver prompts/config por tabla simple |
| Tiempo real (WebSocket/SSE) | **Resuelto por no-requisito** | Interacción HTTP request/response + polling; no dependencia obligatoria de WS observada. [HECHO] | Bajo | Baja | [OPCIÓN ALTERNATIVA] mantener polling en v1 |

## C. Qué ya está mejor de lo que pensábamos

1. **Superficie moderna desacoplada de legacy**: `/api/interfaz_usuario` no depende de `/chat`/`/negociar` legacy; incluso hay tests específicos de “no fuga”. [HECHO]
2. **Contrato de trazabilidad de entrada** (`entry_surface`, `entrypoint`, snapshot de config por turno), útil para auditoría funcional y futura integración LMS. [HECHO]
3. **Arquitectura LLM modular** por pipeline/config/prompts en carpetas separadas (`chat` vs `negociacion`). [HECHO]
4. **Degradación operativa**: si faltan credenciales OpenAI/Google, hay fallbacks explícitos en varias rutas (no rompe todo el servicio). [HECHO]
5. **Paralelización parcial ya implementada** (memory + phase classifier) y trazas detalladas de latencias/nodos. [HECHO]

## D. Qué falta realmente (confirmado)

1. **Persistencia durable mínima** para sesiones y feedback.
2. **Estrategia de concurrencia por sesión** (evitar carrera de dos requests simultáneas sobre mismo `session_id`).
3. **Definición operativa de despliegue Railway** (start command/Procfile equivalente y contrato de envs productivas).
4. **Cerrar o aislar ruta/avatar legacy** para evitar colisión multiusuario por IDs hardcoded.

## E. Qué podría dejarse para una segunda fase

1. Redis distribuido (si se arranca con una sola instancia).
2. Separación a microservicios/workers dedicados (si volumen inicial bajo).
3. Refactor completo de escenarios (puede empezar por parametrización ligera).
4. Realtime con WebSockets/SSE (no imprescindible en estado actual).

## F. Qué sería inaceptable dejar como está

1. Publicar v1 multiusuario usando **`avatar_app` con IDs hardcoded**.
2. Prometer continuidad/reanudación fuerte sin persistencia (reinicio borra estado).
3. Escalar a múltiples réplicas con estado en RAM sin mecanismo compensatorio.

## G. Camino mínimo viable (realista) para v1 Railway

### Objetivo v1 (aceptable, no ideal)

- 1 instancia Railway.
- UI oficial: `/interfaz_usuario`.
- Estado en RAM **solo temporal**, con alcance “sesión activa/no garantizada tras reinicio”.
- Feedback opcional: activo solo para demos o desactivado en producción inicial.

### Cambios mínimos necesarios (sin reingeniería total)

1. Definir comando de arranque Railway con `uvicorn` y `PORT`.
2. Configurar env vars y secretos; usar solo OpenAI al inicio si simplifica STT.
3. Restringir/sacar de uso `avatar_app` legacy en entorno público.
4. Documentar y aplicar política de `session_id` única por usuario/actividad/intento.
5. Añadir persistencia mínima cuando se abra a uso evaluable (al menos turnos + estado canónico).

## H. Recomendación final

- **Tocar primero**:
  1. Superficie de entrada productiva (usar solo `/api/interfaz_usuario` + IDs robustos).
  2. Persistencia mínima de sesiones/turnos.
  3. Arranque Railway y secretos.
- **No tocar todavía**:
  - reescritura total a arquitectura distribuida,
  - Redis/colas avanzadas si no hay escalado horizontal inmediato.
- **Ya suficientemente bien para v1 (con límites explícitos)**:
  - motor de negociación/orquestación,
  - separación de prompts y config por flujo,
  - frontend embebido,
  - guardrails/trazas.

---

## Respuesta directa a las 3 preguntas finales

### 1) ¿Qué cosas importantes para Railway ya existen (aunque imperfectas)?

- Backend FastAPI completo con rutas funcionales.
- Superficie moderna de API (`/api/interfaz_usuario`) más segura que legacy.
- Configuración modular de pipelines y prompts.
- Manejo por variables de entorno y degradación por fallback.
- Servicio monolítico válido para comenzar en una sola instancia.

### 2) ¿Qué cosas faltan de verdad para una v1 aceptable y viable?

- Definición operativa de despliegue (`PORT/start command`) y hardening de entorno.
- Política sólida de identidad de sesión en cliente/servidor.
- Evitar uso productivo de `avatar_app` legacy hardcodeado.
- Persistencia mínima si se exige continuidad/reanudación o evaluación formal.

### 3) ¿Qué partes podrían mantenerse como están por ahora sin impedir despliegue razonable ni futura integración Moodle?

- Pipeline cognitivo de negociación y guardrails.
- Estructura monolítica (API + static) en una primera etapa.
- RAM para caches transitorias (p.ej., cache TTS) con límites operativos.
- Jobs en-proceso para entornos pequeños/piloto, siempre que no se vendan como durables.

