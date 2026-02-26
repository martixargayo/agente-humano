# V08 — Cambio de persona para reducir sesgo “siempre preguntar”

## A) Qué se afirma que cambió
- Se sustituyó el rasgo de persona que empujaba “one question per turn”.
- Nuevo rasgo permite alternancia: a veces pregunta, otras valida y cede iniciativa.
- Objetivo: reducir interrogatorio desde el contexto de identidad del agente.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/elementos/render/carlos_buyer_preset.py`
  - `CARLOS_PERSONA_PROFILE["trait_markers"]`

## C) Evidencia 1 — Diff / Snippets (con contexto)
```python
# backend/negotiation/elementos/render/carlos_buyer_preset.py
"trait_markers": [
    "sometimes asks one focused question; other times validates and yields initiative",
    ...
]
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "trait_markers|sometimes asks one focused question|asks one focused question per turn" backend/negotiation/elementos/render/carlos_buyer_preset.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- El perfil de persona se inyecta en `full_profiles_block` del executor prompt.
- Por tanto, el cambio se refleja en contexto del LLM sin imponer reglas duras.

## F) Evidencia 4 — Telemetría / LiveTrace2
- No existe campo específico de “trait used”; efecto se infiere por prompt render y comportamiento observado.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: cambio de una sola línea puede ser insuficiente si otras capas siguen empujando preguntas.
- Mitigación ya aplicada: stack de prompting anti-interrogatorio y turn-taking.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Trait marker actualizado en preset.
- [ ] No queda la frase antigua literal en el archivo.

Reproducción:
```bash
rg -n "sometimes asks one focused question|asks one focused question per turn" backend/negotiation/elementos/render/carlos_buyer_preset.py
```
