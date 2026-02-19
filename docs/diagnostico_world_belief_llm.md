# Diagnóstico detallado: pipeline LLM de `world` y `belief`

## 1) Resumen ejecutivo (qué está pasando y por qué puede “no detectar señales”)

El sistema **sí tiene múltiples capas de encasillado** (gating + allowlists + normalización + clamps + merge conservador). Esto mejora estabilidad, pero también puede producir sensación de “no detecta señales” en casos borde.

Los principales puntos que pueden estar recortando señal son:

1. **Gating de world**: no siempre llama al LLM; sólo abre si hay intervalo, cambio material de forma de input o cambio fuerte de interacción.
2. **Allowlist estricta de keys en world_domain**: cualquier key fuera de `ALLOWED_UNIVERSAL_DOMAIN_KEYS` y `ALLOWED_NEGOTIATION_DOMAIN_KEYS` se elimina.
3. **Normalización dura de `open_claims`**: rechaza claims sin `label` válido snake_case, sin `evidence_text`, o con `scope/category` fuera de conjunto permitido.
4. **Gating de belief**: también puede saltarse updates; depende de `world_diff`, flags críticas, fingerprint, tono, etc.
5. **Belief conservador**: métricas con `step clamp` y razones con allowlist fija + top-6; evita swings, pero reduce sensibilidad.
6. **`interaction_health` bloqueado**: por implementación actual, no se permite cambiar porque `_interaction_strong(...)` devuelve siempre `False`.
7. **`conversation_mode`**: si no es `negotiation`, se vacían partes de señal de negociación (en world y belief).

---

## 2) Arquitectura de extremo a extremo (paso a paso)

### Paso A — Entrada del turno

En `world_updater_node` se recibe mensaje de usuario, estado previo y metadatos. Se calculan:

- `input_shape_features(...)`
- `extract_interaction_signals(...)`
- `interaction_fingerprint(...)`

Con eso se decide si ejecutar extractor world o saltarlo por gate.

### Paso B — Gate de world (decisión de llamar/no llamar LLM)

`gate_world(...)` abre world LLM sólo si ocurre al menos una de estas condiciones:

- expiró `WORLD_REFRESH_INTERVAL_TURNS` (por defecto 3), o
- cambió materialmente la forma del input, o
- hubo cambio fuerte en señales de interacción (`implicit_acceptance`, `escalation_signal`, `loop_hint`, `evasion_detected`).

Si no, devuelve `extractor_mode=none` y el estado world queda igual.

### Paso C — Llamada al LLM de world

Si el gate abre, `update_world_state(...)` llama `extract_world_patch_llm_v4(...)`, que delega en `v3` para extracción y postprocesa metadata.

El prompt de world obliga JSON estricto con:

- `universal_domain_patch`
- `negotiation_domain_patch`
- `universal_patch`
- `open_claims`

### Paso D — Filtro de keys permitidas (allowlists)

Tras respuesta del LLM, el extractor **elimina** keys no permitidas:

- `ALLOWED_UNIVERSAL_DOMAIN_KEYS`
- `ALLOWED_NEGOTIATION_DOMAIN_KEYS`

Esto significa que si el modelo detecta una señal útil pero la devuelve con una key nueva/no prevista, esa señal desaparece del patch.

### Paso E — Normalización world

Luego se hace merge y normalización:

- `merge_universal_state(...)` limita tamaños y resuelve conflictos por score/confidence.
- `normalize_open_claims(...)` filtra claims inválidas y deduplica.
- `normalize_world_state_v2(...)` fuerza contrato de schema.

### Paso F — Cálculo de `world_diff`

Se compara estado previo vs nuevo para producir `world_diff` (base para gate de belief y otros nodos).

### Paso G — Gate de belief

`belief_updater_node` ejecuta `gate_belief(...)`. Si no hay delta suficiente + no venció intervalo, puede saltar update de belief.

### Paso H — Llamada LLM belief

Si abre gate, `update_belief_state(...)` llama `extract_belief_patch_llm_v3(...)` (prompt v2), recibe:

- `universal_patch`
- `negotiation_patch`
- `meta`

con `schema_version="belief_updater_v2"` obligatorio.

### Paso I — Merge conservador de belief

- Métricas (`trust/cooperation/clarity/engagement`) con step clamp (`max_step_metrics`).
- `reasons` con allowlist fija y top-6 priorizado.
- `negotiation_patch` sólo si modo negociación o señales presentes (según prompt + lógica).
- Si `conversation_mode != negotiation`, se fuerza `neg_patch = {}`.

---

## 3) Cómo funcionan exactamente las LLM de world y belief

## 3.1 Config y modelos efectivos

`get_world_llm()` y `get_belief_llm()` construyen `ChatOpenAI` desde `NegotiationModelConfig`.

Defaults:

- world: `gpt-4.1-nano`, temp 0.0, timeout 18s, max_tokens 384.
- belief: `gpt-4.1-nano`, temp 0.0, timeout 18s, max_tokens 384.

Admiten overrides por env `NEGOTIATION_WORLD_*` y `NEGOTIATION_BELIEF_*` (incluyendo `TOP_P`, penalties, retries, seed, etc.).

## 3.2 Prompting de world

- System prompt: extractor JSON estricto, sin texto extra, sin inventar keys.
- User prompt incluye: `conversation_mode`, `user_message`, `prev_world_state_json`, `belief_state_json`, reglas y allowlists.

Esto **encasilla intencionalmente** para robustez de parsing/contrato.

## 3.3 Prompting de belief

- System prompt: updater conservador de JSON.
- Universal exige estructura fija de métricas/dynamics/tom/reasons.
- `reasons` sólo admite keys permitidas: `tone_shift`, `evasion_signal`, `boundary_signal`, `loop_signal`, `commitment_signal`, `cooperation_signal`, `clarity_signal`.

Si aparece señal fuera de ese vocabulario, se pierde o se colapsa en otra key.

---

## 4) “Keys y allowed”: inventario preciso

## 4.1 ALLOWED en world_domain

### Universal domain (`ALLOWED_UNIVERSAL_DOMAIN_KEYS`)

- `message_is_vague`
- `tone_signal`
- `tone_confidence`

### Negotiation domain (`ALLOWED_NEGOTIATION_DOMAIN_KEYS`)

- `price_mentioned`, `price_value`, `price_firm`, `price_firm_text`
- `deadline_claimed`, `deadline_text`, `deadline_days`, `deadline_kind`
- `urgency_claimed`, `urgency_text`, `urgency_reason`
- `other_buyer_claimed`, `other_buyer_text`, `other_buyer_offer_price`, `other_buyer_timing_text`
- `concession_made`, `concession_text`
- `batna_claimed`, `batna_text`
- `min_price_claimed`, `min_price_text`
- `docs_claimed`, `docs_types`
- `evidence_offered`, `evidence_text`

Cualquier key fuera de esta lista se descarta.

## 4.2 Allowed en `open_claims`

- `scope` permitido: `universal|negotiation|other_domain`
- `category` permitida: `emotion|social_dynamics|tactic|risk|identity|preference|constraint|context|quality|other`
- `label`: regex `^[a-z][a-z0-9_]{0,31}$`
- además requiere `evidence_text` no vacío.

Si no cumple, el claim no entra.

## 4.3 Allowed en belief reasons

Lista cerrada de keys para reasons universales:

- `tone_shift`
- `evasion_signal`
- `boundary_signal`
- `loop_signal`
- `commitment_signal`
- `cooperation_signal`
- `clarity_signal`

También se limita a top-6 por score/prioridad.

---

## 5) Dónde “se rellena” cada cosa (mapa de datos)

- `universal_domain` y `negotiation`: salen del patch world + filtros allowlist.
- `universal_state`: sale de `universal_patch`, mergeado con histórico y normalizado.
- `open_claims`: salen del LLM pero pasan por filtros estrictos y dedupe.
- `belief.universal`: se rellena por patch belief + merge conservador (clamps).
- `belief.negotiation`: merge profundo limitado, pero se vacía fuera de modo negociación.
- `*_meta` (`extractor_meta`, `belief_update_meta`) guardan trazas de decisión/fallo/salto.

---

## 6) Restricciones y hard limits que más afectan sensibilidad

1. **Intervalos de refresh (`WORLD_REFRESH_INTERVAL_TURNS`, `BELIEF_REFRESH_INTERVAL_TURNS`)**.
2. **Heurística de cambio material** en gate (si no detecta cambio, no hay llamada).
3. **Allowlists cerradas** en world domain y reasons belief.
4. **`open_claims` con validación fuerte** (regex + evidencia + enum).
5. **Clamps de métricas** en belief (`max_step_metrics`).
6. **`_interaction_strong` devuelve False**: bloquea cambios de `interaction_health`.
7. **Modo conversación** no-negociación borra patch de negociación.

---

## 7) Hipótesis priorizadas de por qué ahora cuesta detectar señales

1. **Gate no abre** lo suficiente en turnos “parecidos” (especialmente voz o mensajes cortos repetitivos).
2. **Señales nuevas no mapeadas a keys allowlist** y se descartan silenciosamente.
3. **`open_claims` inválidas por etiqueta/categoría/evidencia** y quedan fuera.
4. **Belief demasiado conservador** (clamps + top-6 reasons + vocabulario cerrado).
5. **Conversación no clasificada como negotiation** en momento clave y se vacían parches.
6. **Dependencia de marcadores regex/lexicales** para interacción/tone, con cobertura limitada.

---

## 8) Checklist de depuración operativo (paso a paso)

1. Verificar en trace por turno:
   - `extractor_meta.extractor_skipped`
   - `extractor_meta.skip_reason`
   - `world_gate_features.changed_keys`
   - `world_gate_features.interaction_changed_fields`
2. Verificar si el LLM devolvió keys fuera de allowlist:
   - comparar JSON raw extractor vs patch final.
3. Auditar rechazos de `open_claims`:
   - label regex, scope/category, evidence_text.
4. Revisar `conversation_mode` en cada turno:
   - si no es `negotiation`, negotiation_patch se vacía.
5. Revisar `belief_update_meta`:
   - skip/fail/error, `uni_patch_keys`, `negotiation_patch_keys`.
6. Revisar si hay saturación de clamps:
   - métricas siempre pegadas a cambios mínimos.
7. Revisar cobertura de marcadores (`FRIENDLY/TENSE/CONFLICT/EVASION/...`).

---

## 9) Conclusión

Tu hipótesis de “muy encasilladas” es técnicamente consistente con el diseño actual: el pipeline privilegia estabilidad/contrato frente a sensibilidad. El sistema tiene varios embudos (gates, allowlists, normalización, clamps) que pueden estar podando señales reales.

El diagnóstico más probable es una combinación de:

- **gate conservador + vocabulario de keys cerrado + validadores estrictos**,

más que un fallo único del modelo base.

---

## 10) Respuesta específica: ¿existe hoy un canal para “improvisar” señales no predefinidas?

Sí, pero **sólo de forma parcial**.

### Lo que sí existe

1. **`open_claims`**: permite capturar señales no necesariamente mapeadas a las keys duras del dominio (`universal_domain` / `negotiation`).
2. **`world_state_meta.unknown_claims`**: existe como contenedor/meta para claims desconocidos (p. ej., rutas no registradas en el índice de evidencia).

### Lo que no existe (o no está activo para el core world/belief)

1. No existe un mecanismo que tome automáticamente esas señales “improvisadas” y las promueva a nuevas keys estructurales en `universal_domain` o `negotiation` en runtime.
2. No existe una expansión dinámica de allowlists en caliente para que nuevas keys pasen por el extractor sin cambios de código.
3. En belief, `reasons` también está cerrado por allowlist, así que señales fuera de vocabulario no se preservan como razones canónicas.

### Por qué, en la práctica, parece que “no se usa”

Porque el pipeline separa dos carriles:

- **Carril canónico (decisiones de política/gating/estado duro):** depende de keys predefinidas y normalizadas.
- **Carril abierto (`open_claims`/unknown):** sirve como memoria de señal extra, pero no gobierna directamente los campos estructurados críticos.

Resultado: la LLM puede “ver” o incluso emitir señales nuevas, pero si no entran en el carril canónico, no impactan tanto en el comportamiento del sistema.
