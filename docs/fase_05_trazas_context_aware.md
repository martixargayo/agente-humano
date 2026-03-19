# Fase 05 — trazas context-aware

## 1. Propósito exacto de la fase

Hacer visible en trazas y metadatos qué contexto oficial produjo cada turno.

Esta fase ocurre aquí porque ya se necesita una sesión con contexto fijo para poder escribir trazas fiables.

---

## 2. Qué se cambia exactamente

Se enriquece la observabilidad del turno con identidad contextual:

- `context_id`
- `context_version`
- `context_pack_hash` o equivalente
- baseline oficial vs baseline + overrides

No se cambia lógica negociadora.

---

## 3. Archivos concretos implicados

### Archivos actuales a tocar

- `backend/negociacion/orchestration/turn_contract.py`
- `backend/negociacion/orchestration/flow_config.py`
- `backend/negociacion/traces/models.py`
- `backend/negociacion/traces/builders.py` si hace falta resumen contextual
- `backend/negociacion/optimizador/services.py`
- `backend/negociacion/optimizador/trace_reader.py`
- `backend/interfaz_usuario/services.py`

### Archivos nuevos posibles

- `backend/negociacion/traces/context_meta.py` si se quiere encapsular helpers de serialización contextual

---

## 4. Cambios exactos archivo por archivo

### `backend/negociacion/traces/models.py`

- **Responsabilidad hoy:** definir `TurnTrace` y `PromptArtifacts` sin identidad contextual oficial.
- **Cambio exacto:** añadir campos compatibles para `context_id`, `context_version`, `context_pack_hash` y quizás `official_context_used`.
- **Compatibilidad:** nuevos campos opcionales inicialmente para no romper traces legacy.

### `backend/negociacion/orchestration/flow_config.py`

- **Responsabilidad hoy:** crea `TurnTrace` y congela prompts/artifacts por turno.
- **Cambio exacto:** inyectar en la traza los metadatos del contexto ya resuelto para el turno actual.
- **Compatibilidad:** no altera ejecución de nodos ni payloads de planner/executor.

### `backend/negociacion/orchestration/turn_contract.py`

- **Responsabilidad hoy:** adjuntar `_entry_contract` con surface, entrypoint y snapshot de config.
- **Cambio exacto:** ampliar `_entry_contract` o metadata asociada para incluir el contexto oficial usado por el turno.
- **Compatibilidad:** conservar los campos actuales y solo ampliar payload.

### `backend/negociacion/optimizador/services.py`

- **Responsabilidad hoy:** añadir metadata `_optimizador` a la última traza.
- **Cambio exacto:** añadir identidad de contexto base además de overrides y versión del workspace.
- **Compatibilidad:** mantener estructura actual y extenderla.

### `backend/negociacion/optimizador/trace_reader.py`

- **Responsabilidad hoy:** listar turns sin awareness contextual oficial.
- **Cambio exacto:** exponer contexto en listados/resúmenes de turns para comparaciones seguras.

### `backend/interfaz_usuario/services.py`

- **Cambio exacto:** opcionalmente exponer `context_id` en metadata devuelta por bootstrap/turn si sirve para diagnóstico, sin romper clientes existentes.

---

## 5. Estructura nueva que aparecería en esa fase

Posible helper nuevo:

```text
backend/
  negociacion/
    traces/
      context_meta.py
```

---

## 6. Qué NO se toca todavía

- resolución pública final si aún está en transición;
- pipeline de evaluación;
- estructura profunda del optimizer beyond metadata;
- lógica negociadora;
- finish button;
- prompts/assets baseline.

---

## 7. Cómo se garantiza equivalencia funcional

- las trazas cambian solo en metadata, no en decisiones del motor;
- prompts efectivos del baseline no cambian;
- JSON efectivos no cambian;
- state táctico no cambia;
- API pública puede seguir igual si los campos nuevos son opcionales o internos;
- evaluación visible no cambia todavía;
- optimizer baseline sigue igual, pero ahora mejor identificado.

---

## 8. Riesgos específicos de la fase

- tener sesiones context-aware pero trazas todavía ambiguas;
- escribir contexto distinto en trace y en `_entry_contract`;
- olvidar reflejar que un turno fue baseline + overrides y no baseline puro.

---

## 9. Validaciones y checks recomendados

- ejecutar baseline y comprobar que la traza incluye `context_id` correcto;
- ejecutar sandbox con overrides y comprobar coexistencia de contexto base + overrides;
- verificar que traces legacy sigan parseando si los nuevos campos son opcionales.

---

## 10. Condición de salida

Cada turno de negociación puede identificarse inequívocamente por contexto oficial y distinguirse de turnos con overrides experimentales.

---

## 11. Rollback / compatibilidad

Mantener nuevos campos como opcionales y aditivos permite desactivar su lectura sin romper generación de trazas legacy.
