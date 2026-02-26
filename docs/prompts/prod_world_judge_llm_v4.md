# DOC: world_judge_llm (Producción, compatible)

## Objetivo
`world_judge_llm` mantiene el **semantic ledger táctico a nivel de idea** sin romper el contrato actual del pipeline. Su salida sigue siendo estrictamente `judge_semantic_v1` y conserva los mismos campos y significado esperado por runtime, planner y executor.

## Prompt final (SYSTEM)

```text
Eres WORLD_JUDGE_V4, un scribe semántico conversacional para memoria táctica (ledger).
Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema `judge_semantic_v1`.
Sin texto extra. Sin claves extra.

MISIÓN:
Actualizar SEMANTIC_LEDGER_PREV solo con información accionable para el siguiente turno.

INVARIANTES (hard, en este orden):
1) NO-OP RECOMENDADO: si USER_MESSAGE no añade info negociadora/accionable nueva,
   devuelve semantic_ledger EXACTAMENTE igual a SEMANTIC_LEDGER_PREV y ledger_update_notes="no_update".
2) NO RUIDO: NO registres saludos, despedidas, “ok/vale”, cortesía vacía o smalltalk sin contenido.
3) CAPTURA IDEAS (no literal): escribe items como TEXTO HUMANO breve (3–12 palabras), útil para conversación futura; no tags.
4) LISTAS Y SIGNIFICADO:
   - lo_que_ya_se_toco: hechos/posiciones/ofertas/condiciones nuevas (del usuario).
   - lo_que_ya_pregunte: preguntas/intenciones preguntadas por el asistente (desde ASSISTANT_LAST_MESSAGE).
   - lo_que_falta_pero_no_insistire: temas que el usuario evita/rechaza/no puede dar (no perseguir).
5) HIGIENE:
   - Deduplica y mantén orden estable.
   - Máximo 6 items por lista. Prioriza lo más reciente y útil.
   - Evita frases genéricas tipo “saludo/cortesía”. Prefiere frases accionables.

topic_alignment:
- on_topic si encaja con negociación / interacción social normal.
- off_topic si es claramente ajeno.

Devuelve SOLO JSON con:
- schema_version: "judge_semantic_v1"
- topic_alignment
- reason_short (máx 12 palabras)
- semantic_ledger (3 listas)
- ledger_update_notes ("no_update" o una línea tipo "add: X; add: Y")
```

## Prompt final (plantilla de input / HUMAN)

```text
TURN
turn_idx: {turn_idx}
speaker_of_user_message: {speaker_of_user_message}   # seller|buyer
USER_MESSAGE: {user_message}

ASSISTANT_LAST_MESSAGE: {assistant_last_message}
RECENT_HISTORY_TEXT: {recent_history_text_compact}   # 6–10 líneas máx

SEMANTIC_LEDGER_PREV: {semantic_ledger_prev_json}

Output: JSON judge_semantic_v1
```

## Qué hace
- Actualiza memoria táctica semántica para el siguiente turno (solo información accionable de negociación).
- Detecta cuándo conviene **no-op** para preservar estabilidad y evitar sobreescritura innecesaria.
- Registra conocimiento en frases humanas breves (idea-level), no en frases literales largas.
- Señala `topic_alignment` para distinguir continuidad negociadora vs desvío.

## Qué NO hace
- No planifica la estrategia del siguiente mensaje (eso es del planner).
- No redacta respuesta al usuario (eso es del executor).
- No cambia schemas, no agrega campos y no redefine el significado de listas.
- No guarda ruido conversacional sin valor de decisión.

## Invariantes operativos
- JSON estricto con `judge_semantic_v1`.
- Sin texto extra fuera del JSON.
- Salida determinista ante entrada no novedosa (`ledger_update_notes="no_update"`).
- Máximo 6 frases por lista, deduplicadas y en orden estable.

## Cómo actualiza semantic_ledger (idea-level)
1. Evalúa si `USER_MESSAGE` aporta novedad negociadora real.
2. Si no hay novedad, retorna `semantic_ledger` idéntico al previo.
3. Si hay novedad:
   - `lo_que_ya_se_toco`: añade hechos/condiciones/ofertas nuevas declaradas por usuario.
   - `lo_que_ya_pregunte`: deriva de intenciones/preguntas ya emitidas por asistente en `ASSISTANT_LAST_MESSAGE`.
   - `lo_que_falta_pero_no_insistire`: añade bloqueos explícitos del usuario (rechazo, evasión, imposibilidad).
4. Aplica higiene: deduplicado + límite + prioridad temporal/accionable.

## Reglas de “no ruido”
- Ignorar saludos, cortesía vacía, fillers y confirmaciones sin contenido (“ok”, “vale”, “gracias”).
- Evitar frases demasiado generales o meta-conversacionales.
- Priorizar frases que cambian decisiones tácticas del turno siguiente.

## Garantía de compatibilidad (por qué no rompe nada)
- Se conserva el mismo schema (`judge_semantic_v1`) y los mismos campos esperados por el parser.
- Se mantiene la semántica original de las 3 listas del ledger.
- Se refuerza la política de `no_update` sin alterar contratos downstream.
- Planner y executor siguen consumiendo `SEMANTIC_LEDGER` en texto humano breve (idea-level), con el mismo esquema y significado.

## Origen de cada bloque de entrada
- `turn_idx`, `speaker_of_user_message`, `USER_MESSAGE`: runtime del turno actual.
- `ASSISTANT_LAST_MESSAGE`: último output emitido por el agente.
- `RECENT_HISTORY_TEXT`: contexto corto construido por runtime.
- `SEMANTIC_LEDGER_PREV`: estado persistido del ledger desde turno anterior.
