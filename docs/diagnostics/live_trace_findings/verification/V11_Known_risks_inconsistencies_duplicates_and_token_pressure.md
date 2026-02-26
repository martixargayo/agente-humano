# V11 — Riesgos conocidos: inconsistencias, duplicados y presión de tokens

## A) Qué se afirma que cambió
- Se auditó el estado actual buscando duplicidades/inconsistencias tras los upgrades.
- Se listan hallazgos con evidencia reproducible y recomendaciones sin aplicar cambios.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/elementos/render/executor_prompts.py`
- `backend/prompts.py`
- `backend/negotiation/executor/render_executor.py`
- `backend/negotiation/llm_planning_context.py`

## C) Evidencia 1 — Diff / Snippets (con contexto)
### Hallazgo 1: Doble definición de `SUMMARY_USER_PROMPT`
```python
# backend/prompts.py
SUMMARY_USER_PROMPT = """ ... """   # primera definición
...
SUMMARY_USER_PROMPT = """ ... """   # segunda definición (shim API)
```
Impacto: riesgo de divergencia futura si se modifica solo una.

### Hallazgo 2: Prompt executor muy extenso
```text
# backend/negotiation/elementos/render/executor_prompts.py
[HUMAN-FIRST PRIORITY ...]
[NO-REPEAT BY IDEA]
[RITMO_ANTI_INTERROGATORIO ...]
[CEDER_INICIATIVA ...]
[PROGRESO_POR_TURNO]
[PRICE_PUSHBACK ...]
[PICARDIA_RESPETUOSA]
[COMMON_SENSE_HUMAN_FIRST ...]
[CANAL_Y_ACCIONES_PROHIBIDAS ...]
[ANTI_LITERALIDAD ...]
```
Impacto: presión de tokens y posible competencia entre reglas.

### Hallazgo 3: max_words=30 puede tensionar instrucciones
```text
# executor output schema
- max_words=30, max_questions=1
```
Impacto: responder + validar + avanzar + negociación en 30 palabras puede truncar calidad.

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "^SUMMARY_USER_PROMPT\s*=|REGLAS_MEMORIA_LARGA|NOVEDAD_Y_REPETICION" backend/prompts.py
rg -n "HUMAN-FIRST PRIORITY|NO-REPEAT BY IDEA|RITMO_ANTI_INTERROGATORIO|CEDER_INICIATIVA|PROGRESO_POR_TURNO|PRICE_PUSHBACK|PICARDIA_RESPETUOSA|COMMON_SENSE_HUMAN_FIRST|CANAL_Y_ACCIONES_PROHIBIDAS|ANTI_LITERALIDAD" backend/negotiation/elementos/render/executor_prompts.py
rg -n "max_words=30|max_questions=1|_WORD_CAP_LIMIT" backend/negotiation/elementos/render/executor_prompts.py backend/negotiation/executor/render_executor.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- Runtime incluye reintento por cap de palabras (`_WORD_CAP_RETRY_INSTRUCTION`), indicio de presión de longitud.
- No hay evidencia en tests de degradación por conflicto de bloques; requiere evaluación de calidad conversacional con traces reales.

## F) Evidencia 4 — Telemetría / LiveTrace2
- No hay métrica dedicada para “prompt overload”.
- Sugerencia futura: registrar `executor_prompt_chars` y correlacionar con calidad semántica de salida.

## G) Qué podría estar mal / riesgos detectados (con pruebas)
1. **Duplicidad de summary prompt**
   - Síntoma: dos constantes con mismo nombre.
   - Evidencia: grep de asignaciones duplicadas.
   - Impacto: mantenimiento frágil.
   - Recomendación: consolidar definición única.
2. **Stack de reglas potencialmente redundante en executor**
   - Síntoma: bloques nuevos + legacy superpuestos.
   - Evidencia: grep de headers.
   - Impacto: menor obediencia relativa por saturación.
   - Recomendación: compactar prioridades en una jerarquía más corta.
3. **Tensión palabras máximas vs objetivos múltiples**
   - Síntoma: output cap de 30 palabras.
   - Evidencia: schema + enforcement.
   - Impacto: pérdida de matiz (human-first + edge + pushback a la vez).
   - Recomendación: evaluar subir límite o adaptar estilo por fase (sin rails duros).

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Riesgos identificados con evidencia reproducible.
- [ ] Ningún hallazgo se presenta como bug confirmado sin prueba.
- [ ] Recomendaciones propuestas sin aplicar cambios de código.

Reproducción:
```bash
rg -n "^SUMMARY_USER_PROMPT\s*=" backend/prompts.py
rg -n "HUMAN-FIRST PRIORITY|ANTI_LITERALIDAD|CANAL_Y_ACCIONES_PROHIBIDAS" backend/negotiation/elementos/render/executor_prompts.py
rg -n "max_words=30|_WORD_CAP_LIMIT" backend/negotiation/elementos/render/executor_prompts.py backend/negotiation/executor/render_executor.py
```
