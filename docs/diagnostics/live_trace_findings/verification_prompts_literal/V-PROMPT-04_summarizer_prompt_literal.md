# V-PROMPT-04 — Summarizer prompt literal + uso real

## A) Prompt literal renderizado (completo)

### System prompt
```text
Eres un sintetizador de conversación.
Resume en español, breve y fiel a los hechos.
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
- `backend/agent.py::_summarize_prefix_into_state`

## C) Payload/messages al LLM
- SystemMessage(content=...)
- HumanMessage(content=...)

## D) Evidencia reproducible
```bash
python scripts/dump_literal_prompts.py
```

## E) Confirmación de uso y duplicados
- En `backend/prompts.py` hay 1 definición de SUMMARY_SYSTEM_PROMPT y 1 de SUMMARY_USER_PROMPT tras cleanup.
- El dump se captura ejecutando el camino real de resumen en `backend/agent.py`.
