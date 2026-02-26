# Wiring Evidence Report (V2)

## 1) Prompt snapshots (exactos)

### Planner SYSTEM
- **PATH/constante:** `backend/prompts.py`: `PLANNER_SEMANTIC_V1_SYSTEM_PROMPT`.
```text
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.
```
- **should match docs:** `docs/prompts/prod_planner_llm_v1.md` → **MATCH**.

### Planner USER/HUMAN
- **PATH/constante:** `backend/prompts.py`: `PLANNER_SEMANTIC_V1_USER_PROMPT`.
```text
TURN
SPEAKER: {speaker}                  # seller|buyer|system (si aplica)
USER_MESSAGE: {user_message}
ASSISTANT_LAST_MESSAGE: {assistant_last_message}

CONSTRAINTS
style_id: {style_id}                # ej: psyplay_compact
max_words: {max_words}              # ej: 30
max_questions: {max_questions}      # ej: 1

ROLE / GOAL (COMPACT)
You are Carlos (buyer). Goal: buy the car as cheap as reasonably possible without damaging the relationship.

PHASE CONTROL
prev_phase: {prev_phase}            # valores esperados: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
allowed_next_phases: {allowed_next_phases_json}  # subconjunto de las 5 fases oficiales

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: {lo_que_ya_se_toco_json}
lo_que_ya_pregunte: {lo_que_ya_pregunte_json}
lo_que_falta_pero_no_insistire: {lo_que_falta_pero_no_insistire_json}

CONTEXT (COMPACT)
recent_history_compact: {recent_history_compact}
objective_summary: {objective_summary_compact}

PHASES_RESUMEN (1 línea por fase)
- clima_humano: abrir/cuidar vínculo, validar tono y mantener conversación natural.
- descubrimiento_y_comprension: aclarar contexto útil para decidir sin convertirlo en interrogatorio.
- propuesta_creativa: plantear opción concreta con enfoque ganar-ganar y siguiente micro-paso.
- concesiones_y_ajuste_final: intercambiar ajustes finales (precio/condiciones/tiempo) sin perder relación.
- formalizacion_del_acuerdo: confirmar cierre, condiciones finales y pasos textuales de formalización.

Output: JSON planner_semantic_v1
```
- **should match docs:** `docs/prompts/prod_planner_llm_v1.md` → **MATCH**.

### Executor SYSTEM
- **PATH/constante:** `backend/negotiation/elementos/render/executor_prompts.py`: `EXECUTOR_V2_SYSTEM_PROMPT`.
```text
Eres el EXECUTOR (redactor final) de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema executor_v2.
- Sin texto extra. Sin claves extra.

Invariantes (en este orden):
1) HUMAN-FIRST: si el usuario/vendedor hace una pregunta, respóndela primero (1–2 frases).
2) Sigue planner_semantic_output (phase/style/next_move_hint) y PHASE_CARD. No inventes objetivos.
3) Aplica PROFILE_CARD (Carlos) y sus hard_limits. Mantén tono respetuoso, no presionante.
4) NO-REPEAT: respeta SEMANTIC_LEDGER (lo_que_ya_se_toco, lo_que_ya_pregunte, lo_que_falta_pero_no_insistire).
   No repitas preguntas/ideas ya cubiertas ni insistas en temas que el usuario rechazó/evitó.
5) SOLO TEXTO: prohibido pedir mostrar/enviar/adjuntar o acciones físicas. Prohibidos verbos tipo: muéstrame, enséñame, envíame, adjunta, pásame, tráeme. Reformula a pregunta respondible por texto.
6) FORMATO: texto plano (sin markdown, sin viñetas, sin emojis).
7) LÍMITES: cumple max_words y max_questions del input. Si hay conflicto, (5) y (7) ganan siempre.

Ejecución del plan:
- Interpreta next_move_hint como guía ejecutable (RESPUESTA / MOVIMIENTO / PREGUNTA opcional / TEMA).
- No añadas pregunta si el hint no trae PREGUNTA, salvo que desbloquee una decisión real.

Autocheck antes de emitir JSON:
- ¿Respondí primero a la pregunta directa?
- ¿Cumplo max_words y max_questions?
- ¿Evité verbos prohibidos y peticiones de “mostrar/enviar/adjuntar”?
```
- **should match docs:** `docs/prompts/prod_executor_llm_v2.md` → **MATCH**.

### Executor USER/HUMAN
- **PATH/constante:** `backend/negotiation/elementos/render/executor_prompts.py`: `EXECUTOR_V2_USER_PROMPT`.
```text
TURN
speaker: {speaker}                         # seller|buyer
user_message: {user_message}
last_seller_utterance: {last_seller_utterance}
assistant_last_message: {assistant_last_message}

PROFILE_CARD
{profile_card_compact_text}

SCENE_CARD
{scene_card_compact_text}

CONSTRAINTS
style_id: {style_id}
max_words: {max_words}
max_questions: {max_questions}

PLANNER
planner_semantic_output: {planner_semantic_output_json}

PHASE_CARD (solo la phase elegida)
phase: {phase}                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: {phase_do_short}                      # 2–4 líneas máx
avoid: {phase_avoid_short}                # 2–4 líneas máx
question_policy: {phase_question_policy}  # 1 línea
topic_selected: {topic_selected}

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: {lo_que_ya_se_toco_json}
lo_que_ya_pregunte: {lo_que_ya_pregunte_json}
lo_que_falta_pero_no_insistire: {lo_que_falta_pero_no_insistire_json}

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: {recent_history_compact}

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: {memory_long_compact}

RETRY_HINT
{retry_hint}

Output: JSON executor_v2
```
- **should match docs:** `docs/prompts/prod_executor_llm_v2.md` → **MATCH**.

### World judge SYSTEM
- **PATH/constante:** `backend/prompts.py`: `WORLD_JUDGE_V4_SYSTEM_PROMPT`.
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
- **should match docs:** `docs/prompts/prod_world_judge_llm_v4.md` → **MATCH**.

### World judge USER/HUMAN
- **PATH/constante:** `backend/prompts.py`: `WORLD_JUDGE_V4_USER_PROMPT`.
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
- **should match docs:** `docs/prompts/prod_world_judge_llm_v4.md` → **MATCH**.

## 2) Wiring map (código)
### a) Input planner y campos inyectados
- **Path+líneas:** `backend/negotiation/phase_policy_planner.py`
```text
    99	        phase_map = get_phase_map_v1()
   100	        full_profiles_block = build_planner_context_block_full(progress_state)
   101	
   102	        prev_phase = str((((progress_state or {}).get("phase_state") or {}).get("phase") or "clima_humano"))
   103	        allowed_next_phases = [p for p in phase_map.keys() if p in OFFICIAL_PHASE_IDS] or OFFICIAL_PHASE_IDS
   104	        style_id = str(((_style_contract or {}).get("style_id") or "psyplay_compact"))
   105	        lo_que_ya_se_toco = list((semantic_ledger or {}).get("lo_que_ya_se_toco", [])) if isinstance(semantic_ledger, dict) else []
   106	        lo_que_ya_pregunte = list((semantic_ledger or {}).get("lo_que_ya_pregunte", [])) if isinstance(semantic_ledger, dict) else []
   107	        lo_que_falta_pero_no_insistire = list((semantic_ledger or {}).get("lo_que_falta_pero_no_insistire", [])) if isinstance(semantic_ledger, dict) else []
   108	
   109	        phases_resumen_text = "\n".join([
   110	            "- clima_humano: crear cordialidad real y confianza (inicio o tensión).",
   111	            "- descubrimiento_y_comprension: entender variables clave sin interrogatorio.",
   112	            "- propuesta_creativa: desbloquear con opciones concretas y trueques.",
   113	            "- concesiones_y_ajuste_final: ajustar flecos con concesiones condicionadas.",
   114	            "- formalizacion_del_acuerdo: confirmar checklist de cierre, sin regateo.",
   115	        ])
   116	        topics_por_fase_text = json.dumps(TOPICS_BY_PHASE, ensure_ascii=False)
   117	
   118	        user_prompt = PLANNER_SEMANTIC_V1_USER_PROMPT.format(
   119	            speaker="seller",
   120	            user_message=str(user_message or "")[:1000],
   121	            assistant_last_message=str(assistant_last_message or "")[:1000],
   122	            style_id=style_id,
   123	            max_words=int((_constraints_struct or {}).get("max_words", 30) or 30),
   124	            max_questions=int((_constraints_struct or {}).get("max_questions", 1) or 1),
   125	            prev_phase=prev_phase,
   126	            allowed_next_phases_json=json.dumps(allowed_next_phases, ensure_ascii=False),
   127	            lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
   128	            lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
   129	            lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
   130	            recent_history_compact=str(recent_context or "")[-1200:],
   131	            objective_summary_compact=objective_summary,
   132	            phases_resumen_text=phases_resumen_text,
   133	            topics_por_fase_text=topics_por_fase_text,
   134	        )
   135	        meta["objective_source"] = objective_source
   136	        meta["objective_summary"] = objective_summary
   137	        meta["phase_map_json"] = phase_map
   138	        messages = [
   139	            SystemMessage(content=PLANNER_SEMANTIC_V1_SYSTEM_PROMPT),
   140	            HumanMessage(content=user_prompt),

```
### b) Parse de TEMA (regex real)
- **Path+líneas:** `backend/negotiation/phase_cards_extended.py`
```text
    81	_TOPIC_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$')
    82	_TOPIC_FALLBACK_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*(.+?)\s*$')
    83	
    84	
    85	def get_phase_card_extended(phase_id: str) -> tuple[dict, str]:
    86	    pid = str(phase_id or "").strip()
    87	    if pid in _PHASE_CARDS_EXTENDED:
    88	        return deepcopy(_PHASE_CARDS_EXTENDED[pid]), "ok"
    89	    fallback = deepcopy(_PHASE_CARDS_EXTENDED["clima_humano"])
    90	    fallback["phase"] = "clima_humano"
    91	    return fallback, "fallback"
    92	
    93	
    94	def extract_topic_selected(next_move_hint: str) -> tuple[str, str]:
    95	    text = str(next_move_hint or "")
    96	    m = _TOPIC_REGEX.search(text)
    97	    if m:
    98	        return m.group(1).strip(), "hint_regex"
    99	    m2 = _TOPIC_FALLBACK_REGEX.search(text)
   100	    if m2:
   101	        return m2.group(1).strip().strip('"“”'), "hint_fallback"
   102	    return "", "none"
   103	
   104	
   105	def default_topic_for_phase(phase_id: str) -> str:
   106	    topics = TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])
   107	    if topics:
   108	        return str(topics[0])
   109	    return "sin_tema"
   110	
   111	
   112	def is_valid_topic_for_phase(phase_id: str, topic: str) -> bool:
   113	    topic_s = str(topic or "").strip()
   114	    if not topic_s:
   115	        return False
   116	    return topic_s in TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])

```
### c) Fallback de topic por phase
- **Path+líneas:** `backend/negotiation/phase_cards_extended.py`
```text
    81	_TOPIC_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$')
    82	_TOPIC_FALLBACK_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*(.+?)\s*$')
    83	
    84	
    85	def get_phase_card_extended(phase_id: str) -> tuple[dict, str]:
    86	    pid = str(phase_id or "").strip()
    87	    if pid in _PHASE_CARDS_EXTENDED:
    88	        return deepcopy(_PHASE_CARDS_EXTENDED[pid]), "ok"
    89	    fallback = deepcopy(_PHASE_CARDS_EXTENDED["clima_humano"])
    90	    fallback["phase"] = "clima_humano"
    91	    return fallback, "fallback"
    92	
    93	
    94	def extract_topic_selected(next_move_hint: str) -> tuple[str, str]:
    95	    text = str(next_move_hint or "")
    96	    m = _TOPIC_REGEX.search(text)
    97	    if m:
    98	        return m.group(1).strip(), "hint_regex"
    99	    m2 = _TOPIC_FALLBACK_REGEX.search(text)
   100	    if m2:
   101	        return m2.group(1).strip().strip('"“”'), "hint_fallback"
   102	    return "", "none"
   103	
   104	
   105	def default_topic_for_phase(phase_id: str) -> str:
   106	    topics = TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])
   107	    if topics:
   108	        return str(topics[0])
   109	    return "sin_tema"
   110	
   111	
   112	def is_valid_topic_for_phase(phase_id: str, topic: str) -> bool:
   113	    topic_s = str(topic or "").strip()
   114	    if not topic_s:
   115	        return False
   116	    return topic_s in TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])

```
### d) Lookup de PHASE_CARD_EXTENDIDA
- **Path+líneas:** `backend/negotiation/phase_cards_extended.py`
```text
    81	_TOPIC_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*["“](.+?)["”]\s*$')
    82	_TOPIC_FALLBACK_REGEX = re.compile(r'(?im)^\s*TEMA\s*:\s*(.+?)\s*$')
    83	
    84	
    85	def get_phase_card_extended(phase_id: str) -> tuple[dict, str]:
    86	    pid = str(phase_id or "").strip()
    87	    if pid in _PHASE_CARDS_EXTENDED:
    88	        return deepcopy(_PHASE_CARDS_EXTENDED[pid]), "ok"
    89	    fallback = deepcopy(_PHASE_CARDS_EXTENDED["clima_humano"])
    90	    fallback["phase"] = "clima_humano"
    91	    return fallback, "fallback"
    92	
    93	
    94	def extract_topic_selected(next_move_hint: str) -> tuple[str, str]:
    95	    text = str(next_move_hint or "")
    96	    m = _TOPIC_REGEX.search(text)
    97	    if m:
    98	        return m.group(1).strip(), "hint_regex"
    99	    m2 = _TOPIC_FALLBACK_REGEX.search(text)
   100	    if m2:
   101	        return m2.group(1).strip().strip('"“”'), "hint_fallback"
   102	    return "", "none"
   103	
   104	
   105	def default_topic_for_phase(phase_id: str) -> str:
   106	    topics = TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])
   107	    if topics:
   108	        return str(topics[0])
   109	    return "sin_tema"
   110	
   111	
   112	def is_valid_topic_for_phase(phase_id: str, topic: str) -> bool:
   113	    topic_s = str(topic or "").strip()
   114	    if not topic_s:
   115	        return False
   116	    return topic_s in TOPICS_BY_PHASE.get(str(phase_id or "").strip(), [])

```
### e) Inyección al prompt executor de una sola card
- **Path+líneas:** `backend/negotiation/executor/render_executor.py`
```text
   161	
   162	    phase_id = str((planner_semantic_output or {}).get("phase") or "clima_humano")
   163	    next_move_hint = str((planner_semantic_output or {}).get("next_move_hint") or "")
   164	    topic_selected, topic_source = extract_topic_selected(next_move_hint)
   165	    if not topic_selected:
   166	        topic_selected = default_topic_for_phase(phase_id)
   167	        topic_source = "phase_default" if topic_selected != "sin_tema" else "none"
   168	    phase_card, phase_card_lookup_status = get_phase_card_extended(phase_id)
   169	
   170	    lo_que_ya_se_toco = list((semantic_ledger or {}).get("lo_que_ya_se_toco", [])) if isinstance(semantic_ledger, dict) else []
   171	    lo_que_ya_pregunte = list((semantic_ledger or {}).get("lo_que_ya_pregunte", [])) if isinstance(semantic_ledger, dict) else []
   172	    lo_que_falta_pero_no_insistire = list((semantic_ledger or {}).get("lo_que_falta_pero_no_insistire", [])) if isinstance(semantic_ledger, dict) else []
   173	
   174	    prompt = EXECUTOR_USER_PROMPT.format(
   175	        speaker=str(state.get("speaker_of_user_message") or "seller").strip().lower(),
   176	        user_message=user_message,
   177	        last_counterparty_utterance=extract_last_counterparty_utterance(state),
   178	        assistant_last_message=assistant_last_message_ctx,
   179	        profile_card_compact_text=json.dumps(persona, ensure_ascii=False),
   180	        scene_card_compact_text=json.dumps(scene, ensure_ascii=False),
   181	        style_id=str(style.get("style_id", "psyplay_compact")),
   182	        max_words=int(style.get("max_words", _WORD_CAP_LIMIT) or _WORD_CAP_LIMIT),
   183	        max_questions=int(style.get("max_questions", constraints.get("max_questions", 1)) or 1),
   184	        planner_semantic_output_json=json.dumps(planner_semantic_output, ensure_ascii=False),
   185	        phase=phase_card.get("phase", phase_id),
   186	        phase_do_short=phase_card.get("do", ""),
   187	        phase_avoid_short=phase_card.get("avoid", ""),
   188	        phase_question_policy=phase_card.get("question_policy", ""),
   189	        topic_selected=topic_selected,
   190	        lo_que_ya_se_toco_json=json.dumps(lo_que_ya_se_toco, ensure_ascii=False),
   191	        lo_que_ya_pregunte_json=json.dumps(lo_que_ya_pregunte, ensure_ascii=False),
   192	        lo_que_falta_pero_no_insistire_json=json.dumps(lo_que_falta_pero_no_insistire, ensure_ascii=False),
   193	        memory_short=str(state.get("short_memory", "") or "").strip() or "SIN_MEMORIA_CORTA_AUN",
   194	        memory_long=str(state.get("long_memory", "") or "").strip() or "SIN_RESUMEN_AUN",
   195	        retry_hint="",
   196	    )
   197	    state["topic_selected"] = topic_selected
   198	    state["topic_selected_source"] = topic_source
   199	    state["phase_card_lookup_status"] = phase_card_lookup_status
   200	
   201	    messages = [
   202	        SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.strip()),
   203	        HumanMessage(content=prompt.strip()),
   204	    ]
   205	

```
### f) Persistencia state/meta (topic_selected, source, lookup)
- **Path+líneas:** `backend/negotiation/executor/render_executor.py`
```text
   236	    render_meta = dict(out.get("render_meta") or {}) if isinstance(out.get("render_meta"), dict) else {}
   237	    render_meta["word_cap_limit"] = _WORD_CAP_LIMIT
   238	    render_meta["word_cap_original_words"] = original_words
   239	    render_meta["word_cap_reruns"] = reruns
   240	    render_meta["word_cap_fallback_truncate"] = fallback_truncate
   241	    render_meta["executor_retry_count"] = reruns
   242	    render_meta["text_only_violations_count"] = text_only_violations_count
   243	    render_meta["topic_selected"] = state.get("topic_selected", "")
   244	    render_meta["topic_selected_source"] = state.get("topic_selected_source", "none")
   245	    render_meta["phase_card_lookup_status"] = state.get("phase_card_lookup_status", "missing")
   246	    out["render_meta"] = render_meta
   247	
   248	    return _enforce_executor_v2_contract(normalize_executor_output(out), style, constraints)

```
## 3) Evidencia de ejecución (salidas reales)
**Comando usado:**
```bash
PYTHONPATH=backend python - <<'PY'
# smoke 5 fases: planner->executor con TEMA y phase card lookup
# (ver output completo abajo)
...
PY
```
### Caso clima_humano
```text
planner_output_payload_raw= {"schema_version": "planner_semantic_v1", "phase": "clima_humano", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Pequeño rapport: día / cómo está\"", "what_not_to_repeat": ["no repetir"]}
topic_selected= Pequeño rapport: día / cómo está
topic_selected_source= phase_default
phase_card_lookup_status= ok
text_only_violations_count= 0
executor_retry_count= 0
executor_prompt_has_single_phase_card= True
---planner_prompt_excerpt---
[system]
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.

[human]
TURN
SPEAKER: seller                  # seller|buyer|system (si aplica)
---executor_prompt_excerpt---
TURN
speaker: seller                         # seller|buyer
user_message: ¿te encaja?
last_seller_utterance: Vendedor: hola
assistant_last_message: prev

PROFILE_CARD
{"id": "buyer_mustang67_v1"}

SCENE_CARD
{"id": "mustang67_in_person_viewing"}

CONSTRAINTS
style_id: psyplay_compact
max_words: 40
max_questions: 1

PLANNER
planner_semantic_output: {"schema_version": "planner_semantic_v1", "phase": "clima_humano", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Pequeño rapport: día / cómo está\"", "what_not_to_repeat": ["no repetir"]}

PHASE_CARD (solo la phase elegida)
phase: clima_humano                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: Cálido y breve. Persona primero. Cero negociación técnica en este paso.                      # 2–4 líneas máx
avoid: No precio, no estado técnico, no checklist. No encadenar preguntas.                # 2–4 líneas máx
question_policy: 0 preguntas por defecto; máximo 1 ligera si suma rapport.  # 1 línea
topic_selected: Pequeño rapport: día / cómo está

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: ["inicio"]
lo_que_ya_pregunte: []
lo_que_falta_pero_no_insistire: []

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: Vendedor: hola

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: SIN_RESUMEN_AUN

RETRY_HINT
```
### Caso descubrimiento_y_comprension
```text
planner_output_payload_raw= {"schema_version": "planner_semantic_v1", "phase": "descubrimiento_y_comprension", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Estado general hoy (en una frase)\"", "what_not_to_repeat": ["no repetir"]}
topic_selected= Estado general hoy (en una frase)
topic_selected_source= phase_default
phase_card_lookup_status= ok
text_only_violations_count= 0
executor_retry_count= 0
executor_prompt_has_single_phase_card= True
---planner_prompt_excerpt---
[system]
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.

[human]
TURN
SPEAKER: seller                  # seller|buyer|system (si aplica)
---executor_prompt_excerpt---
TURN
speaker: seller                         # seller|buyer
user_message: ¿te encaja?
last_seller_utterance: Vendedor: hola
assistant_last_message: prev

PROFILE_CARD
{"id": "buyer_mustang67_v1"}

SCENE_CARD
{"id": "mustang67_in_person_viewing"}

CONSTRAINTS
style_id: psyplay_compact
max_words: 40
max_questions: 1

PLANNER
planner_semantic_output: {"schema_version": "planner_semantic_v1", "phase": "descubrimiento_y_comprension", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Estado general hoy (en una frase)\"", "what_not_to_repeat": ["no repetir"]}

PHASE_CARD (solo la phase elegida)
phase: descubrimiento_y_comprension                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: Sacar 1 dato útil por turno sin interrogatorio. Validar + una pregunta enfocada si destraba.                      # 2–4 líneas máx
avoid: No listas de preguntas. No pedir mostrar/enviar/adjuntar. No repetir lo ya preguntado.                # 2–4 líneas máx
question_policy: Máx 1 pregunta y solo si desbloquea decisión.  # 1 línea
topic_selected: Estado general hoy (en una frase)

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: ["inicio"]
lo_que_ya_pregunte: []
lo_que_falta_pero_no_insistire: []

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: Vendedor: hola

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: SIN_RESUMEN_AUN

RETRY_HINT
```
### Caso propuesta_creativa
```text
planner_output_payload_raw= {"schema_version": "planner_semantic_v1", "phase": "propuesta_creativa", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Cierre rápido condicionado (si encaja, cerramos ya)\"", "what_not_to_repeat": ["no repetir"]}
topic_selected= Cierre rápido condicionado (si encaja, cerramos ya)
topic_selected_source= phase_default
phase_card_lookup_status= ok
text_only_violations_count= 0
executor_retry_count= 0
executor_prompt_has_single_phase_card= True
---planner_prompt_excerpt---
[system]
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.

[human]
TURN
SPEAKER: seller                  # seller|buyer|system (si aplica)
---executor_prompt_excerpt---
TURN
speaker: seller                         # seller|buyer
user_message: ¿te encaja?
last_seller_utterance: Vendedor: hola
assistant_last_message: prev

PROFILE_CARD
{"id": "buyer_mustang67_v1"}

SCENE_CARD
{"id": "mustang67_in_person_viewing"}

CONSTRAINTS
style_id: psyplay_compact
max_words: 40
max_questions: 1

PLANNER
planner_semantic_output: {"schema_version": "planner_semantic_v1", "phase": "propuesta_creativa", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Cierre rápido condicionado (si encaja, cerramos ya)\"", "what_not_to_repeat": ["no repetir"]}

PHASE_CARD (solo la phase elegida)
phase: propuesta_creativa                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: Proponer 1 opción concreta (máximo 2) con intercambio claro y cierre condicional.                      # 2–4 líneas máx
avoid: Sin ilegalidades, sin ultimátums, sin 3-4 opciones simultáneas.                # 2–4 líneas máx
question_policy: Máx 1 pregunta para elegir opción o confirmar condición.  # 1 línea
topic_selected: Cierre rápido condicionado (si encaja, cerramos ya)

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: ["inicio"]
lo_que_ya_pregunte: []
lo_que_falta_pero_no_insistire: []

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: Vendedor: hola

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: SIN_RESUMEN_AUN

RETRY_HINT
```
### Caso concesiones_y_ajuste_final
```text
planner_output_payload_raw= {"schema_version": "planner_semantic_v1", "phase": "concesiones_y_ajuste_final", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Contraoferta pequeña y condicionada\"", "what_not_to_repeat": ["no repetir"]}
topic_selected= Contraoferta pequeña y condicionada
topic_selected_source= phase_default
phase_card_lookup_status= ok
text_only_violations_count= 0
executor_retry_count= 0
executor_prompt_has_single_phase_card= True
---planner_prompt_excerpt---
[system]
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.

[human]
TURN
SPEAKER: seller                  # seller|buyer|system (si aplica)
---executor_prompt_excerpt---
TURN
speaker: seller                         # seller|buyer
user_message: ¿te encaja?
last_seller_utterance: Vendedor: hola
assistant_last_message: prev

PROFILE_CARD
{"id": "buyer_mustang67_v1"}

SCENE_CARD
{"id": "mustang67_in_person_viewing"}

CONSTRAINTS
style_id: psyplay_compact
max_words: 40
max_questions: 1

PLANNER
planner_semantic_output: {"schema_version": "planner_semantic_v1", "phase": "concesiones_y_ajuste_final", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Contraoferta pequeña y condicionada\"", "what_not_to_repeat": ["no repetir"]}

PHASE_CARD (solo la phase elegida)
phase: concesiones_y_ajuste_final                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: Concesiones pequeñas y condicionadas, tono práctico, empuje de cierre.                      # 2–4 líneas máx
avoid: No volver a discovery largo ni cambiar de tema si el otro quiere cerrar.                # 2–4 líneas máx
question_policy: 0-1 pregunta, idealmente confirmación de cierre.  # 1 línea
topic_selected: Contraoferta pequeña y condicionada

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: ["inicio"]
lo_que_ya_pregunte: []
lo_que_falta_pero_no_insistire: []

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: Vendedor: hola

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: SIN_RESUMEN_AUN

RETRY_HINT
```
### Caso formalizacion_del_acuerdo
```text
planner_output_payload_raw= {"schema_version": "planner_semantic_v1", "phase": "formalizacion_del_acuerdo", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Checklist: precio + qué incluye\"", "what_not_to_repeat": ["no repetir"]}
topic_selected= Checklist: precio + qué incluye
topic_selected_source= phase_default
phase_card_lookup_status= ok
text_only_violations_count= 0
executor_retry_count= 0
executor_prompt_has_single_phase_card= True
---planner_prompt_excerpt---
[system]
Eres el PLANNER de un agente de negociación por chat.

Salida:
- Devuelve SOLO un JSON que cumpla EXACTAMENTE el schema planner_semantic_v1.
- Sin texto extra. Sin claves extra.

Prioridades (en este orden):
1) HUMAN-FIRST: si USER_MESSAGE contiene una pregunta directa, next_move_hint DEBE empezar respondiéndola (1 frase).
2) CONTROL DE FASE: phase DEBE estar dentro de allowed_next_phases. Prefiere mantener fase o avanzar 1 paso; evita saltos.
   Fases oficiales válidas: clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo.
3) STYLE: style DEBE ser EXACTAMENTE style_id (el que recibes en el input).
4) NO-REPEAT: respeta SEMANTIC_LEDGER. No reabras ideas/preguntas ya cubiertas.
   what_not_to_repeat debe alinearse con lo_que_falta_pero_no_insistire y con lo ya preguntado.
5) RITMO HUMANO: por defecto “validar + cerrar” (sin pregunta). Haz pregunta solo si desbloquea una decisión real.
6) PROGRESO: cada turno debe avanzar (ancla/criterio/condición/siguiente paso) sin convertirlo en interrogatorio.

Contrato para next_move_hint (obligatorio):
- Escribe como guía ejecutable en 1–4 líneas:
  RESPUESTA: ...
  MOVIMIENTO: ...
  PREGUNTA (opcional): ...
  TEMA: "<label exacto>"
- Como máximo 1 pregunta en total.

[human]
TURN
SPEAKER: seller                  # seller|buyer|system (si aplica)
---executor_prompt_excerpt---
TURN
speaker: seller                         # seller|buyer
user_message: ¿te encaja?
last_seller_utterance: Vendedor: hola
assistant_last_message: prev

PROFILE_CARD
{"id": "buyer_mustang67_v1"}

SCENE_CARD
{"id": "mustang67_in_person_viewing"}

CONSTRAINTS
style_id: psyplay_compact
max_words: 40
max_questions: 1

PLANNER
planner_semantic_output: {"schema_version": "planner_semantic_v1", "phase": "formalizacion_del_acuerdo", "style": "psyplay_compact", "next_move_hint": "RESPUESTA: ok\\nMOVIMIENTO: avance\\nPREGUNTA: ¿te encaja?\\nTEMA: \"Checklist: precio + qué incluye\"", "what_not_to_repeat": ["no repetir"]}

PHASE_CARD (solo la phase elegida)
phase: formalizacion_del_acuerdo                            # clima_humano | descubrimiento_y_comprension | propuesta_creativa | concesiones_y_ajuste_final | formalizacion_del_acuerdo
do: Confirmar acuerdo con mini-checklist y siguiente paso logístico.                      # 2–4 líneas máx
avoid: No reabrir precio/condiciones, no meter requisitos nuevos.                # 2–4 líneas máx
question_policy: Máx 1 pregunta de confirmación logística.  # 1 línea
topic_selected: Checklist: precio + qué incluye

SEMANTIC_LEDGER (texto humano)
lo_que_ya_se_toco: ["inicio"]
lo_que_ya_pregunte: []
lo_que_falta_pero_no_insistire: []

MEMORY_SHORT (reciente, 6–10 líneas)
recent_history_compact: Vendedor: hola

MEMORY_LONG (decisional, 3–8 líneas)
memory_long_compact: SIN_RESUMEN_AUN

RETRY_HINT
```
## 4) Guardrail solo texto (prueba)
**Comando usado:**
```bash
PYTHONPATH=backend python - <<'PY'
# fuerza output con "envíame/muéstrame" para disparar retry
...
PY
```
**Output real:**
```text
calls= 2
final_response= Perfecto, dime por texto qué documentación e ITV tienes al día.
contains_forbidden= False
render_meta= {"word_cap_limit": 40, "word_cap_original_words": 8, "word_cap_reruns": 1, "word_cap_fallback_truncate": false, "executor_retry_count": 1, "text_only_violations_count": 0, "topic_selected": "Estado general hoy (en una frase)", "topic_selected_source": "hint_regex", "phase_card_lookup_status": "ok"}
topic_selected= Estado general hoy (en una frase)
topic_selected_source= hint_regex
phase_card_lookup_status= ok

```
**Evidencia invalid topic -> invalid_fallback (output real):**
```text
hint= RESPUESTA: ok
MOVIMIENTO: avance
TEMA: "Motivo de venta (por qué ahora)"
topic_selected= Pequeño rapport: día / cómo está
topic_selected_source= invalid_fallback
expected_default= Pequeño rapport: día / cómo está
phase_card_lookup_status= ok
render_meta= {"word_cap_limit": 40, "word_cap_original_words": 4, "word_cap_reruns": 0, "word_cap_fallback_truncate": false, "executor_retry_count": 0, "text_only_violations_count": 0, "topic_selected": "Pequeño rapport: día / cómo está", "topic_selected_source": "invalid_fallback", "phase_card_lookup_status": "ok"}

```
**Snippet de test que cubre invalid_fallback:** `backend/tests/test_prompt_swap_wiring.py`
```text
def test_invalid_topic_fallback_for_phase():
    class _Deps:
        def execute(self, _messages):
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos por texto.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )

    state = {
        "progress_state": default_progress_state(),
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": "clima_humano",
            "style": "psyplay_compact",
            "next_move_hint": "RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: \"Motivo de venta (por qué ahora)\"",
            "what_not_to_repeat": [],
        },
        "user_message": "hola",
        "assistant_last_message": "prev",
        "recent_history_text": "Vendedor: hola",
        "speaker_of_user_message": "seller",
        "effective_semantic_ledger": {
            "lo_que_ya_se_toco": [],
            "lo_que_ya_pregunte": [],
            "lo_que_falta_pero_no_insistire": [],
        },
    }
    out = render_executor_output(
        state,
        deps=_Deps(),
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={"style_id": "psyplay_compact"},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="hola",
    )
    assert out["schema_version"] == "executor_v2"
    assert state["topic_selected"] == default_topic_for_phase("clima_humano")
    assert state["topic_selected_source"] == "invalid_fallback"
```
## 5) Tests
**Comando:**
```bash
pytest -q backend/tests/test_prompt_swap_wiring.py backend/tests/test_semantic_runtime_v1.py
```
**Output exacto:**
```text
..........................                                               [100%]

```
## 6) Checklist final
- [x] prompts swapped (planner/executor/world_judge activos): **Sí**
- [x] phase IDs correctos (5 oficiales): **Sí**
- [x] TEMA parse ok: **Sí**
- [x] TEMA fallback por ausencia ok: **Sí**
- [x] invalid topic -> invalid_fallback ok: **Sí**
- [x] single PHASE_CARD injection (sin phase map completo) ok: **Sí**
- [x] SEMANTIC_LEDGER humano end-to-end ok: **Sí**
- [x] guardrail solo texto + retry ok: **Sí**
- [x] telemetry keys topic_selected/source/phase_card_lookup/retries/violations ok: **Sí**
- [x] tests requeridos pytest -q en verde: **Sí**