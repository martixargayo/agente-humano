# Auditoría técnica previa a tuning de latencia (`conversacion_simple`) — 2026-04-10

> Alcance explícito: **sin cambios de configuración/modelo**, sin optimizaciones todavía, sin analizar continuidad con `previous_response_id`.

## 1) Resumen ejecutivo

- El brain construye su entrada con un mensaje `developer` (prompt del contexto) + un mensaje `user` que incluye `BrainInput` serializado dentro de `<brain_input_json>...</brain_input_json>`.
- La parte más pesada del prompt no es solo el prompt de texto, sino también los assets embebidos en `BrainInput` (`persona`, `conversation_brief`, `phase_cards`).
- En `baseline`, el input total medido en muestra sintética ronda ~2.8k–3.3k chars por turno; en `negociacion_sala_reuniones` ~66k chars por turno (muy superior).
- `BrainOutput` incluye un bloque `observability.rationale_summary` (campo de “explicación” extra), definido en schema.
- Ese bloque no participa en la lógica principal de aplicación de estado ni en la respuesta visible al usuario; es accesorio para observabilidad/diagnóstico.
- Dado el schema estricto normalizado, `observability` y `rationale_summary` se fuerzan como requeridos en el schema enviado al provider.

## 2) Prompt/prefijo real y estabilidad

### 2.1 Estructura exacta enviada al brain

1. Mensaje `developer`: contenido de `brain_prompt.txt` del contexto activo.
2. Mensaje `user`: wrapper fijo + JSON de `BrainInput`.

Wrapper user fijo:

```text
<task_input>
Devuelve solo JSON válido para `BrainOutput`.

<brain_input_json>
{...BrainInput.model_dump_json()...}
</brain_input_json>
</task_input>
```

### 2.2 Qué parte es fija vs variable

**Fija (por contexto):**
- plantilla del wrapper de usuario,
- estructura de `BrainInput` (keys),
- prompt `brain_prompt.txt`,
- assets del contexto (`persona`, `conversation_brief`, `phase_cards`) salvo que se cambien archivos.

**Variable siempre por turno:**
- `user_turn` (texto + timestamp),
- `recent_dialogue_short`,
- `memory_working`,
- `conversation_state`,
- `memory_compacted_summary`,
- `trace_meta.turn_id`.

**Variable a veces:**
- tamaño/contenido de `memory_compacted_summary` (influido por summarizer),
- composición de `recent_dialogue_short` según trimming.

### 2.3 Estabilidad del prefijo (evidencia de tamaños)

Mediciones sintéticas ejecutadas con `build_brain_messages`:

- `baseline`:
  - `developer_chars`: 1075
  - `brain_input_json_chars`: 1653 → 2064 (0 a 8 mensajes recientes)
  - `total_input_chars`: 2841 → 3252
- `negociacion_sala_reuniones`:
  - `developer_chars`: 14455
  - `brain_input_json_chars`: 51577 → 51988
  - `total_input_chars`: 66145 → 66556

Conclusión: el prefijo es **muy estable** dentro del mismo contexto y sesión (salvo variables de estado), y hay una base estática grande, especialmente en `negociacion_sala_reuniones`.

## 3) Schema de salida exacto (`BrainOutput`)

Campos top-level:
- `schema_version`
- `status`
- `assistant_response.text`
- `state_patch`:
  - `conversation_state`
  - `memory_working`
  - `memory_episodic_append[]`
- `observability.rationale_summary`

Nota técnica importante:
- El modelo Pydantic define `observability` con default factory (puede faltar al validar localmente).
- Pero el schema que se envía al provider pasa por normalización strict y marca todos los `properties` como `required`, incluyendo `observability` y `rationale_summary`.

## 4) Campo de “explicación” extra

Campo identificado:
- `observability.rationale_summary`

Origen:
- Definido en `BrainObservability` del schema (`brain_node.py`).
- No viene del prompt como texto libre adicional post-proceso.
- No lo añade una transformación posterior.

Uso funcional:
- La respuesta al usuario se toma de `assistant_response.text`.
- El estado canónico se aplica desde `state_patch`.
- `observability` no se usa para decidir reply ni patch en el runtime principal.

## 5) Prescindibilidad del campo y ahorro potencial

### 5.1 Dependencia funcional

Imprescindibles para funcionamiento principal:
- `assistant_response.text`
- `state_patch.conversation_state`
- `state_patch.memory_working`
- `status`

Accesorios/no críticos en runtime principal:
- `observability.rationale_summary`
- `memory_episodic_append` (útil para memoria, pero puede estar vacío según turno)

### 5.2 Medición de coste marginal (muestras sintéticas)

Sobre payload de prueba:
- `rationale_summary=None` y `"ok"` -> mismo tamaño (473 chars, por longitud similar en serialización JSON)
- `rationale_summary="explicación breve"` -> +15 chars
- `rationale_summary` larga -> +73 chars en la muestra

Interpretación:
- Si ese campo lleva texto elaborativo frecuente, sí suma tokens de salida.
- Si va `null` o muy corto, impacto pequeño.

## 6) `text.verbosity` (análisis técnico, sin implementar)

Verificación técnica (docs oficiales OpenAI):
- GPT-5.4 soporta `text.verbosity` (`low|medium|high`) y el default documentado es `medium`.
- Está diseñado para reducir/aumentar longitud de salida.
- No se observó incompatibilidad explícita documentada con Structured Outputs (`json_schema strict`).

Riesgo principal en este flujo:
- Con schema estricto, la estructura debe cumplirse; `verbosity=low` tendería a acortar especialmente textos libres (`assistant_response.text`, `event_summary`, `rationale_summary`) pero no debería eliminar keys requeridas.

## 7) `max_output_tokens` (análisis técnico, sin implementar)

Tiene sentido técnico en este flujo porque:
- la salida es JSON estructurado (acotable),
- hoy no hay límite explícito.

Riesgo:
- límite demasiado bajo => JSON incompleto / respuesta `incomplete` por `max_output_tokens`.

Estimación razonada desde muestras:
- payloads válidos de prueba están alrededor de ~390–490 chars (~98–123 tokens aprox usando /4 chars-token como regla gruesa).
- pero producción puede variar (texto de usuario y patches más largos).

## 8) `reasoning.effort` (análisis técnico, sin implementar)

Estado actual brain: `low`.

Trabajo del brain que sí requiere razonamiento:
- seleccionar táctica conversacional,
- mantener coherencia con estado/memoria,
- producir patch consistente.

Trabajo más mecánico:
- formato JSON,
- rellenado de campos estructurales.

Prueba futura razonable (diagnóstico):
- comparar `low` vs `none` con guardas de calidad sobre:
  - coherencia de `state_patch`,
  - calidad conversacional de `assistant_response.text`,
  - tasa de fallbacks/parse errors.

## 9) Otras palancas menores detectadas (mismo modelo)

- Complejidad del prompt por contexto (gran diferencia baseline vs sala reuniones).
- Tamaño de assets inyectados en `BrainInput` (persona/brief/phase_cards) domina input en sala reuniones.
- `memory_compacted_summary` puede crecer hasta `compacted_summary_max_chars` y aumentar input del brain.
- `recent_dialogue_short_max_messages` influye en payload (aunque efecto menor frente a assets grandes en sala reuniones).

## 10) Riesgos por ajuste (sin ejecutar)

- Reducir verbosidad: puede sobre-acortar `assistant_response.text` y degradar naturalidad.
- Límite de output agresivo: riesgo alto de JSON truncado.
- Bajar reasoning a `none`: potencial pérdida de calidad táctica/coherencia en turnos ambiguos.
- Eliminar campos del schema: rompe contratos de tests si no se ajustan primero.

## 11) Prioridad sugerida para futura A/B (no implementada)

Orden técnico sugerido para menor riesgo incremental:
1. Medir coste real de `rationale_summary` (manteniéndolo pero forzando respuestas cortas/null en prompt/schema futuro).
2. Probar `text.verbosity=low` con esquema intacto.
3. Probar `max_output_tokens` con margen amplio sobre P95 medido.
4. Probar `reasoning.effort=none` solo tras tener métricas de calidad y estabilidad.

## 12) Archivos inspeccionados

- `backend/conversacion_simple/orchestration/pipeline.py`
- `backend/conversacion_simple/orchestration/flow_config.py`
- `backend/conversacion_simple/nodes/brain_node.py`
- `backend/conversacion_simple/nodes/common.py`
- `backend/conversacion_simple/contexts/baseline/prompts/brain_prompt.txt`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/prompts/brain_prompt.txt`
- `backend/conversacion_simple/contexts/baseline/prompts/summarizer_prompt.txt`
- `backend/conversacion_simple/contexts/negociacion_sala_reuniones/prompts/summarizer_prompt.txt`
- `backend/conversacion_simple/contexts/resolver.py`
- `backend/infra/openai/structured_outputs.py`
- `backend/interfaz_usuario/services.py`
- `backend/interfaz_usuario/__init__.py`
- `backend/tests/test_conversacion_simple_phase2_runtime.py`
- `backend/tests/test_conversacion_simple_apply_brain_patch.py`
- `backend/tests/test_conversacion_simple_clean_wiring.py`

Sin instrumentación persistente añadida al código runtime.
