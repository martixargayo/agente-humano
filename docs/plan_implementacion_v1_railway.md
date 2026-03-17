# Plan de implementación v1 para Railway (aterrizado en este repositorio)

## 1. Objetivo de la v1

Dejar una **primera versión viable** del sistema desplegada en Railway con alcance pragmático:

- 1 sola instancia.
- Backend público y funcional sobre FastAPI.
- Superficie pública oficial: `interfaz_usuario` + `/api/interfaz_usuario`.
- Aislar la superficie legacy peligrosa (`/avatar`) del camino público.
- Definir arranque y variables de entorno claras para Railway.
- Política mínima de sesión multiusuario razonable en instancia única.
- Sin prometer reanudación fuerte tras reinicio.
- Mantener base compatible con evolución posterior (persistencia real, escenarios, Moodle).

---

## 2. Decisiones ya fijadas

Estas decisiones ya están cerradas para esta fase y condicionan el plan:

1. Despliegue con **una sola instancia Railway**.
2. Vía oficial de producto: `/interfaz_usuario` y `/api/interfaz_usuario`.
3. Se admite estado en RAM para sesión activa en v1, **con límites explícitos**.
4. No se aborda aún persistencia total ni arquitectura distribuida.
5. Feedback/evaluación puede limitarse o desactivarse si aumenta riesgo de v1.
6. Prioridad: sacar v1 usable antes que perfección arquitectónica.

---

## 3. Superficie pública oficial

### 3.1 Qué será público en v1

**Frontend oficial**
- `GET /interfaz_usuario` (static app principal).  

**API oficial**
- `POST /api/interfaz_usuario/sessions/bootstrap`
- `POST /api/interfaz_usuario/negociacion/new_conversation`
- `POST /api/interfaz_usuario/negociacion/turn`
- Endpoints de feedback (`/api/interfaz_usuario/feedback/...`) sujetos a decisión en sección G.

**Soporte voz**
- `POST /stt_google`
- `POST /tts`
- `POST /tts_openai` (opcional para UI moderna, mantener según necesidad).

### 3.2 Qué queda fuera del camino público

- `GET /avatar` y `backend/avatar_app` **no deben ser superficie pública oficial** en v1.
- Motivo operativo: en `avatar_app` se observa payload hardcodeado (`user_id='web_user'`, `session_id='sesion_demo'`) que facilita colisiones multiusuario si se usa tal cual.

### 3.3 Estrategia recomendada v1 para legacy

Orden de preferencia:
1. **Ocultar/no documentar `/avatar`** y no enlazarlo desde la experiencia pública.
2. En backend, **condicionar mount de `/avatar` por feature flag** de entorno (`ENABLE_AVATAR_APP=0` en Railway).
3. Mantener `/avatar` disponible solo en desarrollo interno si se necesita.

> Para v1, esta medida reduce riesgo sin reescritura de `avatar_app`.

---

## 4. Cambios mínimos necesarios

> Esta sección define solo cambios orientados a “Railway v1 viable”, no fase 2.

### CM-01 — Definir arranque Railway explícito
- **Objetivo**: garantizar boot consistente del ASGI app en Railway.
- **Necesidad**: hoy no hay archivo de arranque versionado (Procfile/railway.toml) en repo.
- **Propuesta v1**:
  - Opción simple: configurar start command en panel Railway:
    - `cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}`
  - Opción más reproducible: añadir `Procfile` en raíz con comando equivalente.
- **Bloqueante**: Sí.

### CM-02 — Definir superficie pública oficial y aislar legacy
- **Objetivo**: evitar exposición de `/avatar` como camino principal.
- **Necesidad**: reducir riesgo multiusuario por IDs hardcoded en legacy.
- **Propuesta v1**:
  - Añadir flag de entorno para montar/no montar `/avatar` y `/optimizador`.
  - Documentación pública solo de `/interfaz_usuario` + `/api/interfaz_usuario`.
- **Bloqueante**: Sí (si habrá usuarios reales externos).

### CM-03 — Inventario y saneamiento de variables de entorno
- **Objetivo**: eliminar ambigüedad entre dev y Railway.
- **Necesidad**: existen defaults de desarrollo (ej. `GOOGLE_CREDENTIALS_PATH` local) y flags dispersos.
- **Propuesta v1**:
  - Crear `.env.example` real de producción mínima.
  - Clasificar variables: obligatorias, opcionales, internas/dev.
- **Bloqueante**: Sí.

### CM-04 — Política mínima de sesión para v1 (fase posterior, fuera de scope1)
- **Objetivo**: disminuir colisiones y clarificar contrato de uso.
- **Necesidad**: backend usa `(user_id, session_id)` correctamente, pero el cliente debe garantizar unicidad de `session_id`.
- **Propuesta v1**:
  - `user_id`: identidad funcional del usuario (en v1 puede ser pseudónimo estable por cliente).
  - `session_id`: generado por frontend al iniciar conversación (UUID/ULID), y rotado con `new_conversation`.
  - Prohibir IDs estáticos compartidos en experiencia pública.
- **Bloqueante**: Sí para multiusuario razonable.

### CM-05 — Decisión explícita sobre feedback en v1 (fase posterior, fuera de scope1)
- **Objetivo**: controlar riesgo operacional.
- **Necesidad**: feedback usa threadpool + repositorio en memoria (no durable).
- **Propuesta v1** (recomendada):
  - Mantener endpoint disponible solo si se comunica como “best effort/no durable”.
  - Alternativa de menor riesgo: ocultar en UI pública y dejarlo interno.
- **Bloqueante**: No, si se desactiva/oculta en v1.

### CM-06 — Ajustes mínimos de entorno local peligroso
- **Objetivo**: evitar fallos por defaults locales en cloud.
- **Necesidad**: path default local para Google creds.
- **Propuesta v1**:
  - No depender de Google STT para go-live inicial (usar fallback OpenAI STT si no hay credencial Google).
  - Documentar que `GOOGLE_CREDENTIALS_PATH` en Railway es opcional en v1.
- **Bloqueante**: No (si se asume OpenAI-only para STT en v1).

---

## 5. Archivos concretos a tocar

> Lista de implementación prevista (cuando se ejecute), no aplicada aún.

### Arranque/infra
1. `Procfile` (nuevo, recomendado)
   - `web: cd backend && uvicorn api.app:app --host 0.0.0.0 --port ${PORT}`
2. Opcional: `railway.toml` (si se quiere infra declarativa en repo).

### Configuración/documentación
3. `backend/.env.example` (crear/completar si no existe)
   - variables obligatorias/opcionales para Railway.
4. `backend/README.md`
   - sección “Deploy Railway v1”.

### Backend runtime (mínimo)
5. `backend/api/app.py`
   - feature flags de mount público para `/avatar` y `/optimizador`.
   - (opcional) reducir superficie demo no oficial si confunde.

### Frontend oficial
6. `backend/interfaz_usuario_app/app.js`
   - asegurar generación/uso de `session_id` único al iniciar.
   - alinear UX con política de sesión v1.

### Frontend legacy (si se mantiene en repo)
7. `backend/avatar_app/app.js` (solo si se decide endurecer internamente)
   - evitar IDs hardcoded, o marcar explícitamente modo demo no productivo.

---

## 6. Plan de implementación por pasos

### Paso 1 — Sellar el contrato de despliegue
1. Definir start command Railway (panel o Procfile).
2. Verificar boot con `PORT` dinámico.
3. Verificar endpoint `GET /health` en Railway.

### Paso 2 — Publicar solo superficie moderna
1. Definir `/interfaz_usuario` como home/documentación oficial.
2. Ocultar/aislar `/avatar` por flag.
3. Verificar que flujos de turnos usan `/api/interfaz_usuario/...`.

### Paso 3 — Variables y secretos
1. Declarar variables obligatorias y opcionales.
2. Cargar secretos en Railway.
3. Verificar comportamiento con y sin Google STT.

### Paso 4 — Política mínima de sesión
1. Establecer norma de `session_id` único por conversación.
2. Aplicar en frontend oficial.
3. Validar con pruebas manuales multiusuario básico (dos navegadores, IDs distintos).

### Paso 5 — Feedback para v1 (decisión final)
1. Elegir: visible público / oculto / desactivado.
2. Si visible: etiquetar como no durable.
3. Si oculto: no mostrar botones/flujo en UI pública.

### Paso 6 — Pruebas de aceptación v1
1. Happy path texto + voz.
2. Concurrencia ligera en una instancia.
3. Reinicio controlado y comprobación de expectativas (estado efímero).

---

## 7. Riesgos aceptados

Riesgos que se aceptan conscientemente en esta v1:

1. **Estado de conversación en RAM**: se pierde al reinicio/redeploy.
2. **Feedback en memoria** (si se mantiene activo): no durable.
3. **Sin escalado horizontal**: no hay consistencia entre réplicas (pero no aplica por decisión de 1 instancia).
4. **Concurrencia no transaccional por sesión**: posible carrera en doble envío simultáneo de misma sesión.

Mitigación v1:
- limitar a 1 instancia,
- serializar envío por sesión desde frontend,
- política de IDs únicos,
- expectativas explícitas en documentación.

---

## 8. Checklist de salida a Railway

### Infra/arranque
- [ ] Start command definido y versionado/documentado.
- [ ] App escucha en `0.0.0.0:${PORT}`.
- [ ] `GET /health` responde `200`.

### Superficie pública
- [ ] `/interfaz_usuario` es la ruta oficial pública.
- [ ] `/api/interfaz_usuario/negociacion/turn` operativo.
- [ ] `/avatar` fuera del camino público (oculto o deshabilitado).

### Secrets/env
- [ ] `OPENAI_API_KEY` configurada.
- [ ] Variables TTS definidas (o defaults validados).
- [ ] Estrategia Google STT definida (con credenciales o fallback OpenAI).

### Sesiones/multiusuario v1
- [ ] `session_id` único por conversación en frontend oficial.
- [ ] Prueba con dos usuarios simultáneos sin mezcla de sesión.
- [ ] Límite de no reanudación tras reinicio documentado.

### Feedback (si aplica)
- [ ] Decisión tomada: activo limitado / oculto / desactivado.
- [ ] Comportamiento documentado acorde a su nivel de garantía.

---

## 9. Preparación mínima para la siguiente fase

Sin entrar en fase 2 completa, dejar ya estas decisiones para no bloquear:

1. **Contrato de identidad extensible**: reservar espacio para `activity_id`, `scenario_id`, `attempt_id` en payloads y trazas.
2. **No acoplar UI pública a legacy**: mantener `/api/interfaz_usuario` como superficie estable para futuro adaptador Moodle.
3. **Persistencia futura incremental**: diseñar cambios v1 para poder sustituir `SESSIONS` por repositorio persistente sin romper contratos externos.
4. **Escenarios**: mantener prompts/config separables por dominio para introducir `scenario_id` sin reescribir el motor.

---

## Anexo A — Variables de entorno propuestas para Railway v1

### Obligatorias
- `OPENAI_API_KEY`

### Recomendadas (con defaults existentes)
- `OPENAI_TTS_MODEL` (default actual: `gpt-4o-mini-tts`)
- `OPENAI_TTS_VOICE` (default actual: `cedar`)
- `OPENAI_TTS_FORMAT` (default actual: `wav`)
- `OPENAI_TTS_SPEED` (default actual: `1.10`)
- `OPENAI_STT_MODEL` (default actual: `gpt-4o-mini-transcribe`)

### Opcionales (si se quiere Google STT real)
- `GOOGLE_CREDENTIALS_PATH`
- `GOOGLE_STT_MODEL`
- `GOOGLE_STT_LANGUAGE`
- `GOOGLE_STT_PUNCTUATION`
- `GOOGLE_STT_ENCODING`

### Flags de producto/recomendados para v1
- `ENABLE_AVATAR_APP=0` (propuesto)
- `ENABLE_OPTIMIZADOR_APP=0` (propuesto)
- `ENABLE_FEEDBACK_DEV_FIXTURES=0`

---

## Anexo B — Decisión recomendada sobre Feedback en v1

Recomendación pragmática:

- **Vía pública v1**: ocultar feedback en UI pública (o dejarlo en modo interno).
- Razón: su almacenamiento actual en memoria añade expectativas de durabilidad que v1 no puede garantizar.
- Beneficio: simplifica operación y reduce incidentes sin tocar el núcleo conversacional.

