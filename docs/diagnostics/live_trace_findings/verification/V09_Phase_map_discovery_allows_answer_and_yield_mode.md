# V09 — Phase map discovery: “responder y ceder” como modo válido

## A) Qué se afirma que cambió
- Se añadió explicitación en fase discovery para permitir modo de alta calidad “responder y ceder iniciativa”.
- Objetivo: evitar que discovery derive en interrogatorio continuo.

## B) Dónde está en el repo (rutas + símbolos)
- `backend/negotiation/phase_map.py`
  - clave `descubrimiento_y_comprension` → `que_hacer_y_como_actuar`

## C) Evidencia 1 — Diff / Snippets (con contexto)
```python
# backend/negotiation/phase_map.py
"descubrimiento_y_comprension": {
    "que_hacer_y_como_actuar": [
        "...",
        "Alternar 3 modos ...",
        "Modo de alta calidad: responder y ceder iniciativa cuando el vendedor ya aportó contexto útil; no convertir discovery en interrogatorio.",
    ],
}
```

## D) Evidencia 2 — Grep / Ripgrep reproducible
```bash
rg -n "responder y ceder iniciativa|descubrimiento_y_comprension|interrogatorio" backend/negotiation/phase_map.py
```

## E) Evidencia 3 — Runtime / Prompt rendering
- `phase_map_json` se inyecta en planner y executor prompt render, por lo que esta guía llega al modelo.
- Se puede inspeccionar en `planner_input_prompt_rendered` / `executor_input_prompt_rendered`.

## F) Evidencia 4 — Telemetría / LiveTrace2
- No hay campo dedicado; evidencia por prompt render y salida conversacional.

## G) Qué podría estar mal / riesgos detectados
- Riesgo: una sola línea en phase_map no garantiza priorización frente a otras instrucciones del prompt.
- Mitigación ya aplicada: bloques explícitos de ritmo/turn-taking en planner/executor.

## H) Checklist de aprobación (DoD) + cómo reproducir
- [ ] Mensaje “responder y ceder iniciativa” aparece en phase map.
- [ ] `phase_map_json` continúa inyectándose en prompts.

Reproducción:
```bash
rg -n "responder y ceder iniciativa" backend/negotiation/phase_map.py
rg -n "phase_map_json" backend/negotiation/phase_policy_planner.py backend/negotiation/executor/render_executor.py
```
