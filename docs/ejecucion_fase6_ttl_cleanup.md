# Ejecución fase 6 — TTL y cleanup de sesiones

## 1. Resumen ejecutivo

La fase 6 se implementó con una política de ciclo de vida **consciente del uso real de la sesión**, no con TTL ciega.  

La solución introduce tres estados prácticos de tiempo de vida:

- `bootstrap`: sesión recién creada o recién bootstrappeada sin actividad real todavía;
- `active`: sesión con reentrada real o con turnos activos;
- `finalized`: sesión cerrada explícitamente y retenida solo un periodo corto para cleanup seguro.

Además:

- el TTL se renueva en los puntos correctos del flujo;
- las sesiones expiradas reaparecen limpias si se reutiliza el mismo `session_id`;
- el cleanup de finalización no borra agresivamente de inmediato;
- la continuidad OpenAI se conserva mientras la sesión siga viva y se pierde limpiamente cuando la sesión expira por completo.

## 2. Objetivo exacto de la fase 6

Modelar correctamente el lifecycle de sesión para conseguir que:

- una sesión activa no expire a mitad de uso;
- una sesión abandonada expire sola;
- una sesión finalizada no quede indefinidamente como residuo;
- una sesión expirada no reaparezca con estado viejo;
- el cleanup no rompa continuidad legítima mientras la sesión siga viva.

## 3. Arquitectura antes y después

### Antes
- el store ya soportaba `touch()` en Redis;
- pero no existía una política de TTL definida por lifecycle;
- no había renovación sistemática en bootstrap/reentrada/turno;
- no había finalización explícita con TTL corto;
- no había metadatos persistentes de lifecycle.

### Después
- existe un módulo dedicado `sessions/lifecycle.py`;
- cada sesión persiste un bloque `_session_lifecycle` en `world_state`;
- el runtime aplica TTL según `bootstrap`, `active` o `finalized`;
- bootstrap, reentrada, turno y nueva conversación renuevan TTL donde toca;
- existe finalización explícita con retención corta;
- Redis hace cleanup natural por expiración sin necesitar job destructivo adicional.

## 4. Política de TTL elegida

### TTL configurables por entorno
- `SESSION_BOOTSTRAP_TTL_SECONDS`  
  default: `1800` segundos (`30 min`)

- `SESSION_ACTIVE_TTL_SECONDS`  
  default: `43200` segundos (`12 h`)

- `SESSION_FINALIZED_TTL_SECONDS`  
  default: `600` segundos (`10 min`)

### Justificación

#### Bootstrap (`30 min`)
Se eligió corto/moderado porque:
- protege sesiones recién abiertas pero no usadas;
- evita residuos largos de bootstraps accidentales;
- deja margen suficiente para reloads y reentrada inmediata.

#### Active (`12 h`)
Se eligió claramente más largo que el lock porque:
- evita expiración durante periodos normales de uso real;
- cubre reentrada el mismo día;
- reduce riesgo de perder continuidad legítima entre turnos o recargas.

#### Finalized (`10 min`)
Se eligió corto pero no instantáneo porque:
- permite que el cliente reciba estado estable de cierre;
- evita borrado destructivo demasiado temprano;
- limpia residuos pronto si la conversación ya terminó.

## 5. Política de cleanup elegida

### Elección principal
No se hace `delete` inmediato al finalizar.  
Se hace:

1. marcar sesión como `finalized`;
2. persistir ese estado;
3. aplicar TTL corto;
4. dejar que Redis expire la sesión naturalmente.

### Por qué no delete inmediato
Porque es más arriesgado:
- puede romper relectura inmediata tras finalizar;
- puede producir UX rara si el cliente consulta estado justo después;
- hace más difícil auditar el final del lifecycle.

### Por qué sí TTL corto
Porque:
- reduce residuos;
- evita retención indefinida;
- mantiene un cierre más seguro y observable.

## 6. Decisiones y justificación

### Dónde se renueva el TTL

#### Bootstrap / reentrada
`ensure_session()` ahora:
- detecta si la sesión ya existía;
- aplica `bootstrap` si es una sesión nueva sin trazas;
- aplica `active` si es una reentrada o sesión ya viva.

#### Turno
`run_turn()` y `run_sandbox_turn()` ahora:
- aplican TTL activo al adquirir lock;
- vuelven a aplicar TTL activo cuando el estado ya está materializado;
- vuelven a aplicar TTL activo al completar el turno.

Esto evita que una sesión activa expire mientras está siendo usada.

#### Nueva conversación
Las sesiones creadas con `new_conversation` reciben TTL `active`, porque la intención del usuario ya es operativa y no meramente exploratoria.

#### Finalización
`finalize_session()` marca la sesión como finalizada y le aplica TTL corto.

### Cómo se evita la reanimación rara
Si Redis expiró la key del snapshot:
- `get()` devuelve `None`;
- un bootstrap posterior crea un `SessionState` nuevo y limpio;
- no reaparece `conversation_id`, bindings o canónico previos.

### Cómo se evita cleanup destructivo
No se purgan sesiones activas automáticamente.
La expiración natural depende del TTL de actividad real, no de un cleanup agresivo separado.

## 7. Archivos tocados

- `backend/sessions/lifecycle.py`
- `backend/sessions/state.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/interfaz_usuario/models.py`
- `backend/negociacion/optimizador/services.py`
- `backend/api/app.py`
- `backend/tests/test_phase6_phase7_session_lifecycle.py`

## 8. Riesgos evitados

- sesión recién bootstrappeada quedándose viva indefinidamente;
- sesión activa perdiéndose por ausencia de renovación de TTL;
- sesión finalizada retenida demasiado tiempo;
- reuso de `session_id` con residuos viejos tras expiración;
- pérdida silenciosa de lifecycle al no persistir metadatos mínimos;
- interacción ciega entre lock y expiración del snapshot.

## 9. Riesgos que siguen abiertos

- si Redis estuviera degradado y fallara `expire`, la limpieza natural dependería del estado real del backend Redis;
- la finalización explícita existe en backend, pero el frontend público aún no la invoca automáticamente;
- no hay un background janitor extra porque Redis TTL ya cubre el cleanup principal; esto es deliberado, no un olvido.

## 10. Impacto en continuidad OpenAI

### Positivo
- mientras la sesión está viva, la continuidad OpenAI queda mejor protegida porque el TTL se renueva en reentrada y actividad real;
- la sesión no “muere” por falta de touch durante caminos normales.

### Deliberado
- cuando la sesión expira de verdad, también expira su continuidad OpenAI persistida localmente;
- si se reutiliza el mismo `session_id`, la sesión reaparece limpia, sin heredar `conversation_id` viejo.

Ese comportamiento es el correcto para evitar contaminación.

## 11. Impacto en residuos/contaminación

El impacto es claramente favorable:

- menos residuos de bootstraps abandonados;
- menos sesiones activas sin TTL renovado;
- menos probabilidad de reusar estado antiguo tras expiración;
- lifecycle más observable en `world_state["_session_lifecycle"]`.

## 12. Tests ejecutados

- `pytest backend/tests/test_phase6_phase7_session_lifecycle.py backend/tests/test_phase4_phase5_session_runtime.py backend/tests/test_railway_multiuser_readiness.py backend/tests/test_phase3_context_session_binding.py`
- `python -m py_compile backend/sessions/lifecycle.py backend/sessions/session_lock.py backend/sessions/redis_store.py backend/sessions/state.py backend/interfaz_usuario/services.py backend/interfaz_usuario/__init__.py backend/interfaz_usuario/models.py backend/negociacion/optimizador/services.py backend/api/app.py backend/tests/test_phase6_phase7_session_lifecycle.py backend/tests/test_phase4_phase5_session_runtime.py`

## 13. Resultados de tests

La batería cubrió y validó:

1. bootstrap con TTL inicial;
2. renovación de TTL tras turno exitoso;
3. expiración de sesión inactiva;
4. finalización con TTL corto;
5. no reanimación con residuos tras expiración;
6. nueva conversación limpia tras expiración;
7. continuidad conservada mientras se renueva TTL;
8. restart lógico + Redis + reentrada;
9. coexistencia de TTL de sesión y TTL del lock.

Todos los tests pasaron.

## 14. Conclusión honesta

La fase 6 queda **bien resuelta para el objetivo real actual**:

- hay política de TTL explícita;
- hay cleanup prudente;
- se evita la mayor parte del riesgo de residuos;
- y no se ha introducido una limpieza agresiva que pueda romper continuidad legítima.

Lo pendiente no es la mecánica central, sino integrar mejor la finalización en UX y observar su uso real en despliegue.

## 15. Resumen súper detallado de cambios

### `backend/sessions/lifecycle.py`
- **Qué toqué:** módulo nuevo para TTL/lifecycle.
- **Por qué:** separar la política de lifecycle del store y del servicio de negocio.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí.
- **¿Prepara fases futuras?:** sí, especialmente rollout y observabilidad.
- **¿Modifica comportamiento o solo endurece?:** modifica comportamiento de lifecycle de forma controlada.

### `backend/sessions/state.py`
- **Qué toqué:** `save_session_state()` actualiza `last_updated` de forma consistente.
- **Por qué:** alinear persistencia y lifecycle en todos los stores.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** sí, de forma positiva.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece persistencia.

### `backend/interfaz_usuario/services.py`
- **Qué toqué:** TTL en bootstrap/reentrada/turno/nueva conversación y finalización explícita.
- **Por qué:** aquí vive el lifecycle público real.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí.
- **¿Prepara fases futuras?:** sí, especialmente cleanup real y rollout.
- **¿Modifica comportamiento o solo endurece?:** modifica lifecycle y endurece.

### `backend/interfaz_usuario/__init__.py`
- **Qué toqué:** endpoint `/sessions/finalize`.
- **Por qué:** exponer cleanup explícito sin delete destructivo.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** sí, pero solo cuando se usa.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** amplía superficie de lifecycle.

### `backend/interfaz_usuario/models.py`
- **Qué toqué:** modelos de request/response para finalización.
- **Por qué:** contrato explícito y tipado.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** indirectamente.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece contrato.

### `backend/negociacion/optimizador/services.py`
- **Qué toqué:** touch de TTL en bootstrap, nueva conversación y turnos sandbox.
- **Por qué:** evitar lifecycle incoherente entre superficies.
- **Tamaño del cambio:** medio.
- **¿Afecta al runtime crítico?:** sí para sandbox.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece lifecycle cross-surface.

### `backend/api/app.py`
- **Qué toqué:** health endpoint de runtime de sesión.
- **Por qué:** observabilidad operativa de TTL/config.
- **Tamaño del cambio:** pequeño.
- **¿Afecta al runtime crítico?:** no directamente.
- **¿Prepara fases futuras?:** sí, especialmente rollout.
- **¿Modifica comportamiento o solo endurece?:** endurece visibilidad.

### `backend/tests/test_phase6_phase7_session_lifecycle.py`
- **Qué toqué:** nueva batería de tests de lifecycle.
- **Por qué:** aportar evidencia ejecutable real.
- **Tamaño del cambio:** grande.
- **¿Afecta al runtime crítico?:** no directamente.
- **¿Prepara fases futuras?:** sí.
- **¿Modifica comportamiento o solo endurece?:** endurece validación.
