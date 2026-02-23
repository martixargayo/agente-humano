# Diagnóstico técnico — LiveTrace2 Turno 6 (solo evidencia del trace)

## 1) Versiones activas confirmadas (con evidencia literal)

### world_judge_llm
- **Estado:** `v1`.
- **Prueba literal (prompt):** `Devuelve SOLO JSON válido con schema v1:`
- **Prueba literal (salida):** `"schema_version": "v1"`

### advisor_llm
- **Estado:** **v2 no confirmable** con este trace.
- **Prueba literal disponible:** `Eres advisor estratégico de negociación. Entregas recomendaciones globales compactas.` y `Devuelve SOLO JSON válido con schema:`
- **Motivo de no confirmación:** no aparece `advisor_v2`, `schema_version` versionado, ni tag de prompt v2 en el bloque capturado.

### planner
- **Estado:** **se saltó** (no ejecutó).
- **Prueba literal:** `planner_llm ... llm_call · skipped`
- **Prueba literal (gate):** `"gate_decision": "skipped"`, `"gate_decision_reason": "continue_same_step_without_planner"`, `"reason_codes": ["continue_policy_reuse"]`

### executor
- **Estado:** usa **`executor_v2`** de salida.
- **Prueba literal (schema):** `"schema_version": "executor_v2"`
- **Perfiles cargados:** **legacy/default**, no preset Carlos/Mustang.
- **Prueba literal (bloque perfiles):** `"persona_id": "default"` y `"scene_id": "default_chat"`

---

## 2) Por qué no entran judge v2 y advisor v2 (sin suposiciones fuera del trace)

Con este trace **no se puede demostrar** si faltan `USE_WORLD_JUDGE_V2` / `USE_ADVISOR_V2` o si existe un bug de wiring exacto en código, porque no hay snapshot de env ni logs de selección de branch de prompt.

### Lo único demostrable aquí
- world_judge llega con prompt v1 explícito (`schema v1`).
- advisor no expone marcador de versión.
- no hay ningún campo que enseñe `feature_flags`, `prompt_selector`, `template_id` o `variant_id`.

### Campo/log que falta para confirmarlo en el próximo trace
- `feature_flags.USE_WORLD_JUDGE_V2` y `feature_flags.USE_ADVISOR_V2` (true/false por turno).
- `world_judge_prompt_variant` (ej: `v1|v2`) y `advisor_prompt_variant`.
- `prompt_template_id` o tag visible en prompt (ej: `WORLD_JUDGE_V2_SYSTEM_PROMPT`, `ADVISOR_V2_SYSTEM_PROMPT`).

---

## 3) Por qué executor cayó en `default_chat` y no Carlos/Mustang

Con este trace no se puede probar el estado interno de `progress_state.render_state` ni si `build_full_roleplay_profiles` fue llamado, porque esos objetos/llamadas no están capturados.

### Lo demostrable
- En el payload del executor, `BLOQUE_PERFILES_COMPLETOS` trae:
  - `PERSONA_PROFILE_JSON ... "persona_id": "default"`
  - `ESCENA_PROFILE_JSON ... "scene_id": "default_chat"`
- Por tanto, al executor **ya le llegó** el fallback/default al momento de renderizar.

### Campo exacto faltante para validar `should_force_carlos`
- `render_state.should_force_carlos` (boolean) en el trace.
- `render_state.selected_persona_id` / `render_state.selected_scene_id`.
- `profile_selection_reason` (ej: `forced_carlos`, `fallback_default_missing_context`).

---

## 4) Inconsistencia de roles/speaker

### Evidencia de ruptura
- En world_extractor: `speaker_of_user_message[REDACTED]: unknown`.
- En executor bloque C: `ULTIMA_FRASE_DEL_VENDEDOR ... Vendedor: Yo no tengo nada que decir, ¿qué me ofreces?`
- En executor bloque D: `MENSAJE_ACTUAL (DEL USUARIO) ... Yo no tengo nada que decir, ¿qué me ofreces?`

### Diagnóstico trazable
El mismo texto aparece simultáneamente como frase del vendedor y como mensaje del usuario; además extractor recibe `unknown`. Eso indica desalineación entre:
- campo de speaker usado por extractor, y
- etiqueta textual que se inyecta en bloques C/D del executor.

### Qué fijar (a nivel de contrato de datos, sin asumir archivo)
- Unificar un `speaker_canonical` por turno (`seller|buyer`) y reutilizar ese mismo valor en world_extractor + executor payload.
- Añadir validación de consistencia en runtime: si C indica `Vendedor:`, D no debe etiquetarse como `DEL USUARIO` sin transformación explícita.

---

## 5) WORLD_EXTRACTOR_V4: signal=true con patch vacío

### Hechos del trace
- Salida: `"schema_version": "world_extractor_v4"`
- Salida meta: `"negotiation_signal_detected": true`
- Patch: todos los buckets vacíos.
- Mensaje actual: `Yo no tengo nada que decir, ¿qué me ofreces?`

### Coherencia
- `negotiation_signal_detected=true` es coherente (hay señal negociadora/pedido de propuesta).
- Patch totalmente vacío es discutible frente a la regla de utilidad de planificación.

### Bucket mínimo esperado
- **`requests`** (mínimo): el hablante pide que la contraparte haga una oferta (`¿qué me ofreces?`).
- `claims` no es el bucket mínimo aquí; el núcleo del acto de habla es solicitud.

### Cambio exacto de regla/prompt para forzar 1 item (>=0.60)
Añadir una regla explícita en el prompt del extractor:
- *“Si `negotiation_signal_detected=true` y el mensaje contiene una petición directa de oferta (patrones como `qué me ofreces`), emite al menos 1 item en `requests` con `raw_text` literal y `confidence >= 0.60`.”*

---

## 6) Diagnóstico de gates

### belief_gate
- Hechos: `"gate_decision_reason": "no_world_delta"`, `"world_changed_meaningfully": false`, `"world_diff_keys": ["domain"]`.
- Evaluación: es **coherente internamente** con su propio input (`world_changed_meaningfully=false`) y con patch vacío del extractor.

### planner_gate
- Hechos: world_judge devolvió `"plan_status": "continue_same_step"` y `"skip_planner": false`.
- Gate input: `"planner_request": "continue_policy"`, `"advance_step": false`, `"judgement_skip_planner": false`.
- Salida gate: `continue_same_step_without_planner` + `continue_policy_reuse`.
- Evaluación: **coherente** con política de reutilización cuando no hay avance de step.

---

## 7) Fixes priorizados (máx 10), limitados a lo que permite inferir el trace

> Nota: el trace no incluye rutas/funciones de código. Por eso, en “archivo/función exacta” se indica **N/D en trace** y el **log/campo** que debe agregarse para hacer trazable el punto en la siguiente corrida.

1. **Forzar trazabilidad de variante de world_judge**
   - Archivo/función exacta: **N/D en trace** (falta metadata de selector).
   - Cambio (1–3 líneas): registrar `world_judge_prompt_variant` y tag literal en prompt (`WORLD_JUDGE_V2_SYSTEM_PROMPT`).
   - Señal esperada en LiveTrace: aparición del tag v2 en `world_judge_llm`.

2. **Forzar trazabilidad de variante de advisor**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: registrar `advisor_prompt_variant` + tag `ADVISOR_V2_SYSTEM_PROMPT`.
   - Señal esperada: advisor con marcador v2 visible.

3. **Snapshot de feature flags por turno**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: loggear `USE_WORLD_JUDGE_V2` y `USE_ADVISOR_V2` en evento raíz del turno.
   - Señal esperada: fields booleanos visibles en LiveTrace.

4. **Trazar selección de perfiles del executor**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: loggear `selected_persona_id`, `selected_scene_id`, `profile_selection_reason`.
   - Señal esperada: diagnóstico directo de por qué cayó en `default/default_chat`.

5. **Exponer estado de forcing Carlos**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: añadir `render_state.should_force_carlos` al payload de auditoría.
   - Señal esperada: valor true/false visible para confirmar gating de preset.

6. **Canonicalizar speaker en un único campo**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: introducir `speaker_canonical` obligatorio y reutilizarlo en extractor + executor.
   - Señal esperada: desaparición de `unknown` cuando el texto viene de `Vendedor:`.

7. **Regla anti contradicción C/D en executor payload**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: validación previa: si C contiene `Vendedor:`, D no puede etiquetarse `DEL USUARIO` sin transformación explícita.
   - Señal esperada: no más duplicidad de rol para la misma frase.

8. **Regla mínima de emisión en world_extractor_v4**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: cuando `negotiation_signal_detected=true` + patrón de petición de oferta, emitir 1 item en `requests` (>=0.60).
   - Señal esperada: `world_buckets_patch.requests` no vacío para este tipo de mensajes.

9. **Meta explicativa para patch vacío**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: agregar `meta.empty_patch_reason` cuando signal=true y no hay items.
   - Señal esperada: auditabilidad de por qué no hubo extracción.

10. **Mayor observabilidad de gating/planner reuse**
   - Archivo/función exacta: **N/D en trace**.
   - Cambio: loggear condición completa de reuse (incluyendo umbral de estancamiento si existe).
   - Señal esperada: explicación directa de cuándo se fuerza planner vs reuse.

---

## Resumen ejecutivo
- **Confirmado:** world_judge en v1; planner saltado; executor schema v2 con perfiles default/default_chat.
- **No confirmable con este trace:** si la causa raíz es env var faltante o branch de código concreto para v2 en judge/advisor.
- **Falla visible de calidad de datos:** speaker inconsistente (`unknown` vs `Vendedor`) y extractor con `signal=true` pero sin item utilizable.
