# agente-humano
Sistema IA con OpenAI Responses API para agente humano conversacional (chat + negociación).

## Arquitectura actual (sin LangChain/LangGraph)

- Pipeline 3-LLM por turno para `chat` y `negociacion`:
  - Summarizer (trimming + summarizing por turnos)
  - Planner (Structured Outputs con JSON Schema estricto)
  - Executor (respuesta final)
- Entrada de voz por Google STT (`/stt_google`).
- Salida de voz por OpenAI TTS (`/tts`, modelo por defecto `gpt-4o-mini-tts`).
- Endpoints conversacionales:
  - `/chat`
  - `/negociar`
