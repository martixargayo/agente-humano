# V05 — Summarizer prompt upgrade (memory_long + novelty)

## A) Qué se afirma que cambió
- `SUMMARY_USER_PROMPT` ahora incluye directrices explícitas para memoria larga útil.
- Se añadió sección de novedad/no repetición para guiar resumen por ideas.
- El prompt duplicado de summary en `backend/prompts.py` fue actualizado en ambas definiciones.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/prompts.py`
  - `SUMMARY_USER_PROMPT` (dos definiciones)
- `backend/negotiation/repo_prompts.py`
  - exporta `SUMMARY_USER_PROMPT`
- `backend/agent.py`
  - usa `SUMMARY_USER_PROMPT` vía import desde `prompts` (flujo legacy)

## C) Evidencia 1 — Diff / Snippets (con contexto)
```text
# backend/prompts.py
REGLAS_MEMORIA_LARGA:
- Resume por IDEAS conversacionales útiles para próximos turnos.
- Incluye hechos, preguntas respondidas, sensibilidad y estado de negociación.

NOVEDAD_Y_REPETICION:
- Marca ideas ya tratadas.
- Señala temas que no conviene volver a preguntar salvo información nueva.
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "REGLAS_MEMORIA_LARGA|NOVEDAD_Y_REPETICION|SUMMARY_USER_PROMPT" backend/prompts.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- En el flujo de summary real del backend, el template `SUMMARY_USER_PROMPT` se usa para formar `{existing_summary}` + `{new_block}`.
- Evidencia de invocación: `summary_prompt = ChatPromptTemplate.from_messages([... CONVERSATION_USER_TEMPLATE ...])` en `backend/agent.py` (flujo legacy).
- Nota: no hay test dedicado en esta PR que inspeccione render de summary en runtime semántico.

## F) Evidencia 4 — Telemetría / LiveTrace2
- No hay campo directo en LiveTrace2 para quality de summary; validación debe ser por evaluación del texto de summary.

## G) Qué podría estar mal / riesgos detectados
- Riesgo real: existen dos definiciones de `SUMMARY_USER_PROMPT` en `backend/prompts.py`; aunque hoy ambas están alineadas, esto puede divergir en futuros cambios.
- Propuesta: consolidar definición única (no aplicado en este paso).

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] `SUMMARY_USER_PROMPT` contiene ambos bloques en el archivo.
- [ ] Flujo de summary usa `existing_summary + new_block`.
- [ ] Se registra riesgo por duplicidad de definición.

Reproducción:
```bash
rg -n "SUMMARY_USER_PROMPT|REGLAS_MEMORIA_LARGA|NOVEDAD_Y_REPETICION" backend/prompts.py backend/agent.py
```
