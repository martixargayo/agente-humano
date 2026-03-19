# Fase 07 — optimizer context-aware

## 1. Propósito exacto de la fase

Convertir el optimizer en un consumidor del **mismo contexto oficial** que el runtime público, manteniendo su capa de overrides por encima del baseline.

Va después de evaluación y trazas porque el optimizer necesita una base contextual oficial y observable para poder compararse con la URL pública de forma honesta.

---

## 2. Qué se cambia exactamente

Se redefine el optimizer como:

- contexto oficial base
- + sesión sandbox con identidad contextual
- + overrides opcionales

En vez de operar solo como bundle temporal implícito.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/negociacion/optimizador/models.py`
- `backend/negociacion/optimizador/__init__.py`
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/session_bridge.py`
- `backend/negociacion/optimizador/experiments_bridge.py`
- `backend/negociacion/optimizador/prompts_bridge.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/negociacion/optimizador/datasets_bridge.py` si se quiere guardar contexto con casos

### Archivos nuevos a crear

- `backend/negociacion/optimizador/context_bridge.py`

---

## 4. Cambios exactos archivo por archivo

### `backend/negociacion/optimizador/models.py`

- **Responsabilidad hoy:** requests/overrides sin contexto oficial explícito.
- **Cambio exacto:**
  - añadir `context_id` opcional a bootstrap y/o sandbox new conversation;
  - si se decide, añadir un request específico para seleccionar contexto base del optimizer.
- **Compatibilidad:** defaults al baseline.

### `backend/negociacion/optimizador/__init__.py`

- **Responsabilidad hoy:** exponer endpoints optimizer y sandbox.
- **Cambio exacto:**
  - mantener endpoints actuales;
  - ampliar bootstrap/overrides para que el optimizer conozca el contexto oficial base;
  - opcionalmente añadir endpoint de selección de contexto base.
- **Compatibilidad:** clientes actuales siguen funcionando con baseline.

### `backend/negociacion/optimizador/services.py`

- **Responsabilidad hoy:** ejecutar sandbox turn desde `build_negotiation_pipeline_config()` + overrides.
- **Cambio exacto:**
  - resolver primero el contexto oficial base de la sesión sandbox;
  - luego aplicar overrides encima;
  - persistir `context_id/context_version` en `_optimizador` metadata y sandbox meta.
- **Compatibilidad:** si no se selecciona contexto, usar baseline.

### `backend/negociacion/optimizador/session_bridge.py`

- **Responsabilidad hoy:** duplicar sesión sandbox sin identidad contextual oficial explícita.
- **Cambio exacto:** heredar y persistir `context_id/context_version` del origen o del contexto seleccionado para el sandbox.

### `backend/negociacion/optimizador/experiments_bridge.py`

- **Responsabilidad hoy:** aplicar overrides sobre bundle base legacy.
- **Cambio exacto:**
  - hacer que copie primero el bundle del contexto oficial base resuelto, no un bundle global implícito;
  - permitir que los overrides se interpreten “sobre contexto X”.
- **Compatibilidad:** para baseline, el bundle copiado debe ser el mismo efectivo que hoy.

### `backend/negociacion/optimizador/prompts_bridge.py`

- **Responsabilidad hoy:** listar prompts desde `PROMPTS_DIR` global.
- **Cambio exacto:** listar prompts del contexto oficial base activo.

### `backend/negociacion/optimizador/trace_reader.py`

- **Cambio exacto:** exponer contexto base y overrides al listar turns.

### `backend/negociacion/optimizador/context_bridge.py`

- **Responsabilidad nueva:** resolver y exponer contexto oficial para el optimizer.

---

## 5. Estructura nueva que aparecería en esa fase

```text
backend/
  negociacion/
    optimizador/
      context_bridge.py
```

---

## 6. Qué NO se toca todavía

- diseño de UI del optimizer más allá de lo mínimo para seleccionar contexto;
- lógica negociadora del runtime;
- phase enum;
- state shape;
- baseline prompts/assets.

---

## 7. Cómo se garantiza equivalencia funcional

- si no se selecciona contexto explícito, el optimizer usa baseline igual que hoy;
- la capa de overrides sigue existiendo;
- el bundle oficial base baseline equivale al actual;
- no cambia la negociación baseline, solo se hace explícito sobre qué contexto corre.

---

## 8. Riesgos específicos de la fase

- optimizer resolviendo bundle base distinto al runtime público;
- sandbox sin contexto fijo pero overrides sí aplicados;
- comparar turns de contextos distintos como si fueran del mismo baseline.

---

## 9. Validaciones y checks recomendados

- ejecutar optimizer baseline sin seleccionar contexto y verificar equivalencia con hoy;
- ejecutar optimizer con contexto baseline explícito y verificar misma salida;
- comprobar que los overrides se aplican sobre el contexto correcto.

---

## 10. Condición de salida

El optimizer puede declarar y trazar con claridad el contexto oficial que está simulando, además de los overrides que aplica encima.

---

## 11. Rollback / compatibilidad

Mantener el modo actual de baseline por defecto mientras la selección explícita de contexto se estabiliza.
