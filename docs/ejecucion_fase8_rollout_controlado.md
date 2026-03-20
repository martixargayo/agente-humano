# Ejecución fase 8 — rollout controlado

## 1. Resumen ejecutivo

La fase 8 no añade una nueva infraestructura grande: aterriza **cómo desplegar con seguridad** lo ya endurecido en fases 3–7.

El rollout propuesto para este repo se basa en:

- TTL configurables por entorno;
- health runtime accionable;
- logs suficientes para observar store, TTL y contención;
- despliegue gradual empezando por configuración conservadora;
- criterios claros de éxito, fallo y rollback mínimo.

## 2. Objetivo exacto de la fase 8

Definir una forma realista de pasar a uso real minimizando riesgo de:

- `session_busy` excesivo;
- expiraciones anómalas;
- pérdida de continuidad;
- reuso raro de sesiones;
- degradación silenciosa del flujo negociador.

## 3. Estrategia de rollout propuesta

### Etapa 1 — desplegar código con configuración conservadora
Desplegar primero el código nuevo manteniendo TTL relativamente amplios:

- `SESSION_BOOTSTRAP_TTL_SECONDS=1800`
- `SESSION_ACTIVE_TTL_SECONDS=43200`
- `SESSION_FINALIZED_TTL_SECONDS=600`
- `SESSION_EXECUTION_LOCK_TTL_SECONDS=180`
- `SESSION_EXECUTION_LOCK_REFRESH_SECONDS=30`
- `SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS=2`

Objetivo:
- maximizar estabilidad;
- minimizar expiraciones agresivas al principio.

### Etapa 2 — validar staging
En staging:
- usar Redis real;
- probar bootstrap, turnos, reentrada, nueva conversación y finalización;
- verificar `/api/health/session-runtime`;
- forzar contención conocida para confirmar `423 session_busy`.

### Etapa 3 — observar producción con foco en logs
Desplegar en producción sin cambiar todavía TTL a valores más agresivos.
Observar:
- contención;
- expiración;
- continuidad;
- errores de envelope;
- comportamiento de Redis ping.

### Etapa 4 — ajustar TTL solo si la observación lo justifica
No bajar TTL por intuición.  
Solo ajustar si los logs muestran:
- demasiados residuos;
- muy pocas reentradas válidas largas;
- o necesidad real de cleanup más rápido.

## 4. Precondiciones para desplegar

Antes de desplegar, deberían cumplirse estas condiciones:

1. Redis ya operativo y validado en Railway.
2. `SESSION_STORE_BACKEND=redis` correctamente configurado.
3. `REDIS_URL` privada funcional.
4. Health endpoint accesible:
   - `/api/health/session-runtime`
5. Logs del deploy disponibles y revisables en Railway.
6. Tests de lifecycle/lock pasando en CI/local.

## 5. Pasos de despliegue

1. Deploy del código nuevo con variables TTL/lock explícitas.
2. Verificar startup:
   - selección de store;
   - `redis_ping` correcto en health runtime.
3. Ejecutar smoke tests manuales:
   - bootstrap público;
   - turno normal;
   - reload/reentrada;
   - nueva conversación;
   - finalizar sesión;
   - contención artificial con dos requests sobre misma sesión.
4. Observar logs durante una ventana corta tras el despliegue.
5. Mantener TTL conservadores al menos durante la primera observación.

## 6. Qué mirar en Railway

### Runtime health
- respuesta de `/api/health/session-runtime`;
- `store_class`;
- `redis_ping`;
- TTL configurados efectivos.

### Logs de backend
- `Configuring Redis session store`
- `Redis session store connectivity check succeeded`
- `session_lock_manager_selected backend=redis`
- `session_ttl_applied`
- `interfaz_usuario_turn_busy`
- `optimizador_turn_busy`
- `redis_session_envelope_decode_error`

### Señales de infraestructura
- reinicios inesperados del servicio;
- latencias anómalas al hablar con Redis;
- errores de networking interno Railway.

## 7. Qué mirar en logs

### Para contención
- frecuencia de `session_lock_busy`
- frecuencia de `interfaz_usuario_turn_busy`
- frecuencia de `optimizador_turn_busy`

### Para lifecycle
- scopes `bootstrap`, `active`, `finalized` en `session_ttl_applied`
- sesiones que se finalizan pero no vuelven a aparecer

### Para continuidad
- reentrada con `conversation_id` conservado;
- ausencia de reuso raro de `conversation_id` tras expiración;
- decode errors de envelope.

## 8. Señales de éxito

El rollout va bien si:

1. `redis_ping` está estable en `ok`.
2. Los bootstraps y turnos normales siguen funcionando.
3. `423 session_busy` aparece solo en colisiones reales y no en uso normal.
4. Las reentradas conservan continuidad cuando la sesión sigue viva.
5. Las sesiones expiradas reaparecen limpias.
6. No aparecen errores de envelope ni pérdidas masivas de continuidad.

## 9. Señales de fallo

Hay que frenar o revisar si ves:

1. picos de `session_busy` en uso normal no concurrente;
2. sesiones activas perdiéndose antes de tiempo;
3. demasiadas reentradas sin continuidad cuando no tocaba;
4. `redis_ping` degradado;
5. errores repetidos de decodificación del envelope;
6. anomalías claras de cleanup o de reuso raro del mismo `session_id`.

## 10. Rollback plan

### Rollback mínimo y pragmático
Si el problema es de lifecycle y no de store:
- subir TTL (`bootstrap`, `active`, `finalized`) a valores más conservadores;
- mantener lock activo;
- seguir observando.

Si el problema es de contención:
- aumentar `SESSION_EXECUTION_LOCK_TTL_SECONDS` si hay turnos realmente largos;
- revisar logs antes de tocar lógica.

Si el problema fuese grave en Redis/session runtime:
- como rollback de emergencia, se puede volver temporalmente a `SESSION_STORE_BACKEND=memory` en staging/dev o en escenarios controlados, sabiendo que se pierde la garantía multi-réplica.

No recomiendo rollback de código inmediato salvo que:
- haya corrupción real de sesiones;
- o pérdida sistemática de continuidad.

## 11. Flags / config recomendadas

### Recomendadas ahora
- `SESSION_BOOTSTRAP_TTL_SECONDS`
- `SESSION_ACTIVE_TTL_SECONDS`
- `SESSION_FINALIZED_TTL_SECONDS`
- `SESSION_EXECUTION_LOCK_TTL_SECONDS`
- `SESSION_EXECUTION_LOCK_REFRESH_SECONDS`
- `SESSION_EXECUTION_LOCK_RETRY_AFTER_SECONDS`
- `SESSION_STORE_BACKEND`
- `REDIS_URL`

### Qué decidí no añadir
No añadí flags extra de “cleanup agresivo” o “delete inmediato” porque:
- complican el rollout;
- aumentan riesgo de cleanup destructivo;
- y todavía no hay evidencia de que hagan falta.

La estrategia actual ya permite rollout gradual ajustando TTL, que es el control más útil y más seguro.

## 12. Conclusión honesta

La fase 8 queda bien cerrada **como plan de rollout aterrizado al repo real**:

- hay configuración concreta;
- hay señales observables;
- hay health endpoint útil;
- hay criterios de éxito/fallo;
- y hay rollback razonable sin inventar infraestructura extra.

No es un documento genérico: está apoyado en los cambios reales hechos en fases 3–7.

## 13. Resumen súper detallado de cambios

### `backend/sessions/lifecycle.py`
- **Qué toqué:** variables de entorno TTL reutilizables para rollout.
- **Por qué:** permitir ajuste gradual sin cambiar código.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí.
- **¿Prepara fases futuras?:** sí, directamente.
- **¿Modifica comportamiento o solo endurece?:** modifica lifecycle de forma configurable.

### `backend/api/app.py`
- **Qué toqué:** endpoint health runtime.
- **Por qué:** soporte directo al rollout y a la observación en Railway.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** no directamente.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece observabilidad.

### `backend/interfaz_usuario/services.py`
- **Qué toqué:** logs de lifecycle/busy/finalize.
- **Por qué:** hacer rollout menos ciego.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece y visibiliza.

### `backend/negociacion/optimizador/services.py`
- **Qué toqué:** parity de lifecycle y logs.
- **Por qué:** evitar rollout parcial ciego en otra superficie.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí para sandbox.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece.

### `docs/ejecucion_fase6_ttl_cleanup.md`
- **Qué toqué:** documentación de lifecycle y cleanup.
- **Por qué:** dejar política explícita y justificable.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** no.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** documenta y endurece criterio.

### `docs/ejecucion_fase7_hardening_tests.md`
- **Qué toqué:** documentación de hardening y cobertura.
- **Por qué:** dejar evidencia y límites claros.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** no.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** documenta y endurece criterio.

### `docs/ejecucion_fase8_rollout_controlado.md`
- **Qué toqué:** plan de despliegue controlado.
- **Por qué:** aterrizar el rollout al repo real.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** no directamente.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** documenta estrategia operativa.
