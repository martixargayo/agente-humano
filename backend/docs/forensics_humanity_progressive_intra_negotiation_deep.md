# Forense estrecho: degradación progresiva de humanidad intra-negociación (`interfaz_usuario` vs `optimizador`)

## 1. Resumen ejecutivo

Se ejecutó una investigación forense **quirúrgica** sobre la hipótesis de deriva progresiva en el tramo `planner -> executor` dentro de una negociación continua.

Resultado:

- En baseline continuo limpio (mismo caso, misma secuencia, mismas condiciones), **no aparece divergencia estructural temprana entre superficies**.
- Al introducir residuo acumulativo solo en interfaz, la primera divergencia aparece inmediatamente en ventana contextual de planner/executor (`...recent_dialogue_len`), y la señal de rigidez (proxy de estilo administrativo) aparece en turnos medios.
- Al aplicar ablación de ventana (clamp a 4) el gap de rigidez desaparece, lo que fortalece causalidad de tipo **acumulación de contexto** y no “otro cerebro”.

Este forense no identifica un nuevo bug duro exclusivo de una superficie en baseline limpio; acota que el cuello de botella residual sigue siendo la **acumulación contextual progresiva** en negociaciones largas.

## 2. Hipótesis

Hipótesis principal: la pérdida de humanidad no nace rota al inicio, sino que emerge como cascada progresiva por residuo acumulativo en inputs efectivos de planner/executor.

## 3. Metodología

- Harness nuevo: `backend/scripts/forensics_humanity_progressive_intra_negotiation.py`
- Captura de payloads efectivos por nodo (`freeze_prompt_artifacts`) + stubs deterministas (`_call_structured`).
- Normalización de ruido efímero (`turn_id`, `timestamp_iso`, summaries textuales).
- Comparación A/B turno a turno en negociación continua (8 turnos):
  - A) baseline continuo limpio,
  - C) residuo oculto solo en interfaz,
  - D) ablación con clamp de ventana contextual.

## 4. Escenarios y evidencia

Artefacto: `backend/docs/forensics_humanity_progressive_intra_negotiation_run.json`.

### Escenario A — baseline continuo limpio
- `A_first_divergence = null`.
- Interfaz y optimizador se mantienen alineados bajo mismas condiciones.

### Escenario C — residuo acumulativo solo en interfaz
- Primera divergencia: turno 1, `executor_recent_dialogue_len` (y ventana planner más larga en interfaz desde el inicio).
- La señal de rigidez aparece en turnos medios (`C_positive_gap_turns = [3]`).

### Escenario D — ablación (clamp de ventana)
- La divergencia de ventana puede seguir visible, pero desaparece la señal de rigidez progresiva (`D_positive_gap_turns = []`).
- Esto sugiere que la ventana acumulativa larga es un driver causal del endurecimiento de realización.

## 5. Primer punto de divergencia

En el patrón con residuo, primer diff estable en:
- `executor_recent_dialogue_len` (y correlato en `planner_recent_dialogue_len`).

## 6. Causalidad (no solo correlación)

Se cumple patrón causal mínimo:
1. baseline limpio sin divergencia;
2. skew acumulativo controlado produce señal de rigidez;
3. ablación de la variable sospechosa (ventana acumulativa) elimina señal de rigidez.

## 7. Qué queda confirmado, qué queda descartado, qué queda abierto

### Confirmado
- La degradación progresiva de humanidad es compatible con acumulación contextual en planner/executor.
- No hace falta “otro cerebro” para reproducirla.

### Descartado (en este forense)
- Divergencia estructural nueva inmediata y estable entre superficies en baseline limpio continuo.

### Abierto
- Medir en producción real (sin stubs) qué subcampo semántico dentro de `selected_memory`/`memory_working` está empujando más la rigidez cuando la ventana crece.

## 8. Ranking de causas

A. Muy probable: acumulación contextual progresiva en negociación larga (ventana + memorias de cierre).
B. Posible: compresión semántica de selected_memory hacia resúmenes más contractuales.
C. Debilitada: asimetría estructural nueva per-surface en baseline limpio.

## 9. Fix aplicado en este ciclo

No se aplicó fix adicional de runtime en este ciclo porque el forense estrecho no encontró una nueva divergencia estructural per-surface en baseline limpio; sí se dejó el caso acotado con causalidad experimental de acumulación y ablación.

## 10. Siguiente paso recomendado

Ejecutar el mismo harness con captura live (sin stub) y score semántico de `selected_memory`/`planner_output.content_plan` para localizar el primer campo semántico que cruza de “humano” a “administrativo” en turnos medios.
