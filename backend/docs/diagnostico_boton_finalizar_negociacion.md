# Diagnóstico exhaustivo: botón **Finalizar negociación** (`avatar_app`)

## Resumen ejecutivo

- El botón `Finalizar negociación` **sí existe en UI** y tiene una señal visual de estado (`is-armed`).
- Su “armado” depende de una bandera de backend (`finish_button_armed`) que viaja en la respuesta de `/negociar`.
- Esa bandera se activa cuando el clasificador de fase detecta:
  - `formalizacion_del_acuerdo`, o
  - `abandono_de_la_negociacion`.
- **Actualmente, hacer click no ejecuta ninguna acción funcional**: solo hace `console.log('finish button clicked')`.
- Además, una vez armado en frontend y backend, el estado es **sticky** (persistente): no se desarma automáticamente en turnos posteriores.

## 1) Dónde nace el botón (frontend)

En `avatar_app/index.html` se declara el botón:

```html
<button id="finishNegotiationBtn" class="finish-negotiation-button" type="button" aria-label="Finalizar negociación">
  Finalizar negociación
</button>
```

El estilo normal y armado (`.is-armed`) está en el mismo archivo.

## 2) Cómo se captura en JS (frontend)

En `avatar_app/app.js`, el botón se referencia en el objeto `ui`:

```js
finishNegotiationBtn: document.getElementById('finishNegotiationBtn'),
```

La clase visual se controla con:

```js
function updateFinishNegotiationButton() {
  if (!ui.finishNegotiationBtn) return;
  ui.finishNegotiationBtn.classList.toggle('is-armed', finishButtonArmed);
}
```

Y el armado se aplica con OR acumulativo:

```js
function armFinishButton(nextArmed) {
  finishButtonArmed = finishButtonArmed || Boolean(nextArmed);
  updateFinishNegotiationButton();
}
```

## 3) De dónde viene `nextArmed` (backend -> frontend)

Cuando se envía un turno (`sendTextTurn`), la app llama `fetchAgentReply(...)`, y luego arma el botón con lo devuelto por backend:

```js
const turnReply = ... await fetchAgentReply(message, { mode: currentAgentMode });
armFinishButton(turnReply.finishButtonArmed);
```

La función que llama backend elige endpoint según modo:

```js
const endpoint = mode === AgentMode.NEGOTIATION ? '/negociar' : '/chat';
```

y mapea la respuesta:

```js
finishButtonArmed: Boolean(data.finish_button_armed),
```

## 4) Endpoint backend y extracción de bandera

En `backend/api/app.py`, el contrato de respuesta incluye:

```py
class ChatResponse(BaseModel):
    reply: str
    finish_button_armed: bool = False
```

### `/chat`
Siempre devuelve `finish_button_armed=False`.

### `/negociar`
Lee estado canónico de negociación y extrae:

```py
ui_state = negotiation_canonical.get("ui_state", {})
finish_button_armed = bool(ui_state.get("finish_button_armed", False))
```

## 5) Lógica real de activación (motor de negociación)

La bandera no se calcula en la API, sino en el pipeline de negociación.

### Regla explícita
En `finish_button_rules.py`:

```py
if canonical_state.planner_state.current_phase == NegotiationPhase.formalizacion_del_acuerdo:
    reasons.append("phase_formalizacion_del_acuerdo")

if canonical_state.planner_state.current_phase == NegotiationPhase.abandono_de_la_negociacion:
    reasons.append("phase_abandono_de_la_negociacion")
```

y luego:

```py
return FinishButtonTriggerEvaluation(should_arm=bool(reasons), reasons=tuple(reasons))
```

### Aplicación al estado (persistente)
En `flow_config.py`:

```py
armed_prev = canonical_state.ui_state.finish_button_armed
trigger_eval = evaluate_finish_button_triggers(canonical_state)
canonical_state.ui_state.finish_button_armed = armed_prev or trigger_eval.should_arm
```

Esto implica: una vez en `True`, queda en `True` para la sesión.

### Momento en que se aplica
En el turno, tras memoria + clasificador de fase:

```py
apply_memory_output_to_state(...)
apply_phase_classifier_output_to_state(...)
apply_finish_button_state(canonical_state)
```

## 6) Cuándo se activa y cuándo no

### Se activa cuando
- El modo de conversación es **Negociación** (usa `/negociar`), y
- el `phase_classifier` deja `current_phase` en:
  - `formalizacion_del_acuerdo` (acuerdo explícito / formalización), o
  - `abandono_de_la_negociacion` (salida explícita sin acuerdo).

### No se activa cuando
- Estás en modo **Chat** (`/chat` fuerza `false`).
- Estás en negociación pero la fase dominante es otra:
  - `clima_humano`
  - `descubrimiento_y_comprension`
  - `propuesta_creativa`
  - `concesiones_y_ajuste_final`
- El clasificador aún no considera evidencia suficiente de formalización/abandono.

## 7) Qué define “formalización” y “abandono”

El prompt del clasificador exige umbral alto:

- `formalizacion_del_acuerdo`: solo con evidencia clara de acuerdo/aceptación explícita.
- `abandono_de_la_negociacion`: solo con salida explícita y foco en cerrar sin acuerdo.
- No se considera abandono por ultimátum condicional o amenaza táctica si la negociación sigue viva.

## 8) Qué hace el click hoy

Actualmente, nada funcional:

```js
ui.finishNegotiationBtn.addEventListener('click', () => {
  console.log('finish button clicked');
});
```

No hay:
- llamada API de cierre,
- reset de sesión,
- navegación,
- lock de input,
- guardado de “negociación finalizada”.

## 9) Conclusión técnica para reutilizar el sistema en otro lugar

El sistema tiene 3 piezas desacopladas:

1. **Detección de “momento de cierre”** (backend / canonical state).
2. **Transporte de señal** (`finish_button_armed` en `/negociar`).
3. **Presentación UI** (clase CSS `is-armed`).

La pieza faltante para “funcione completo” en cualquier superficie es la 4ª:

4. **Acción de finalización** (handler del click + endpoint/flujo de cierre).

Sin esa 4ª pieza, el botón es hoy un **indicador visual de readiness**, no un control transaccional de finalización.
