# V-PROMPT-04 — Summarizer prompt literal + uso real

## A) Prompt literal renderizado (completo)

### System prompt
```text
Eres un sintetizador de conversación en español.
Resume de forma breve, fiel y sin añadir información nueva.
```

### User prompt
```text
Resumen previo:


Bloque nuevo:
Usuario: u0
Agente: a0
Usuario: u1
Agente: a1
Usuario: u2
Agente: a2
Usuario: u3
Agente: a3
Usuario: u4
Agente: a4
Usuario: u5
Agente: a5
Usuario: u6
Agente: a6
Usuario: u7
Agente: a7
Usuario: u8
Agente: a8
Usuario: u9
Agente: a9

REGLAS_MEMORIA_LARGA:
- Resume por IDEAS conversacionales útiles para próximos turnos.
- Incluye explícitamente:
  1) hechos relevantes ya acordados o aclarados,
  2) preguntas ya respondidas,
  3) sensibilidad del interlocutor (temas donde insistir molestó),
  4) estado de negociación actual (sin inventar).
- Evita detalle redundante y evita copiar frases literales largas.

NOVEDAD_Y_REPETICION:
- Marca en el resumen qué ideas ya quedaron suficientemente tratadas.
- Señala qué temas no conviene volver a preguntar salvo nueva información.

Devuelve un único resumen actualizado en texto plano.
```

## B) Dónde se renderiza
- Archivo: `backend/agent.py`
- Camino real ejecutado: `_maybe_trim_and_summarize -> _summarize_prefix_into_state`
- Snippet:
```python
messages = summary_prompt.format_messages(existing_summary=..., new_block=...)
result = summary_llm.invoke(messages)
```

## C) Payload/messages al LLM
- `SystemMessage(content=<system literal arriba>)`
- `HumanMessage(content=<user literal arriba>)`

## D) Evidencia reproducible
```bash
python scripts/dump_literal_prompts.py
python - <<'PY'
import json
obj=json.load(open('docs/diagnostics/live_trace_findings/verification_prompts_literal/prompt_capture.json'))
for m in obj['summary']['messages']:
    print(f"[{m['role']}]\n{m['content']}\n")
PY
```

## E) Confirmación de “no duplicados”
- `backend/prompts.py` contiene 2 definiciones de `SUMMARY_USER_PROMPT` (count=2).
- Este dump demuestra el camino real ejecutado vía `backend/agent.py` con mensajes capturados.
