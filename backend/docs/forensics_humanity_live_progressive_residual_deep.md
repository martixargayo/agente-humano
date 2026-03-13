# Forense estrecho (runtime real): degradación progresiva de humanidad en `interfaz_usuario` vs `optimizador`

## 1) Hipótesis

Hipótesis de trabajo:

> existe arrastre residual acumulativo en `interfaz_usuario` que sesga progresivamente `planner -> executor` hacia formulación más administrativa.

Subhipótesis priorizadas en este ciclo:
1. skew en `recent_dialogue_short` (longitud/composición),
2. skew en `selected_memory` y/o `memory_working.last_turn_summary`,
3. skew expresivo visible en `executor_output.spoken_text`.

---

## 2) Metodología

Script nuevo: `backend/scripts/forensics_humanity_live_progressive_residual.py`.

Características clave:
- comparación A/B por turnos entre superficies,
- captura de payload **real del runtime** por nodo desde `trace.nodes[*].prompt_artifacts.input_payload_json` (sin `_fake_call_structured`),
- separación explícita de divergencias:
  - estructurales,
  - semánticas,
  - expresivas,
- escenarios A/B/C/D con continuidad controlada y ablación dirigida de ventana reciente.

Artefacto generado:
- `backend/docs/forensics_humanity_live_progressive_residual_run.json`.

---

## 3) Escenarios ejecutados

1. **A — baseline limpio controlado**
   - misma secuencia y longitud en ambas superficies;
   - sesiones limpias.

2. **B — negociación continua progresiva**
   - secuencia extendida (turnos medios y tardíos);
   - objetivo: detectar endurecimiento intra-negociación sin intervención artificial.

3. **C — continuidad asimétrica controlada (residuo en interfaz)**
   - pre-siembra de continuidad solo en interfaz;
   - optimizador fresco;
   - objetivo: forzar patrón sospechoso y localizar primer diff.

4. **D — ablación dirigida**
   - mismo patrón de C;
   - ablación mínima sobre ventana reciente (`build_planner_input` y `build_executor_input`, clamp de `recent_dialogue_short`);
   - objetivo: comprobar si desaparece señal posterior.

---

## 4) Primer punto de divergencia

Resultado más sólido de este ciclo (runtime observado):
- en C aparece primer diff estructural en turno 1 en `executor_recent_dialogue_len`;
- A y B no muestran primer diff estructural temprano;
- no emerge primer diff semántico/expresivo en este entorno de ejecución.

---

## 5) Qué queda confirmado

1. **Reproducción live del skew estructural por continuidad asimétrica**:
   - C produce divergencia temprana en longitud de ventana efectiva.
2. **Baseline limpio estable**:
   - A/B no muestran divergencias tempranas entre superficies bajo condiciones comparables.
3. **La familia causal previa no se contradice**:
   - el patrón residual -> skew estructural se sostiene al observar payloads reales del pipeline.

---

## 6) Qué queda descartado en este ciclo

- No hay evidencia de una asimetría estructural nueva en baseline limpio (A/B).
- No hay evidencia en este artefacto de que el problema nazca primariamente en prompts/modelos.

---

## 7) Qué queda abierto

Bloqueador principal de cierre causal final:
- en este entorno no hay `OPENAI_API_KEY`, por lo que el runtime cae a fallback (`client_unavailable`) y no produce señal semántica/expresiva live del modelo.

Implicación:
- este ciclo cierra **estructura** (primer diff estructural),
- pero no puede cerrar **primer diff semántico real** ni **primer diff expresivo real** con modelo live.

---

## 8) Ranking de causas (actualizado)

1. **Líder**: continuidad/residuo asimétrico que ensancha `recent_dialogue_short` en interfaz bajo ciertos patrones de uso.
2. **Siguiente candidata**: composición semántica de memoria seleccionada (`selected_memory`/`last_turn_summary`) cuando la continuidad llega contaminada.
3. **Debilitada**: divergencia basal de runtime por superficie en condiciones limpias.

---

## 9) Validación ejecutada

- Se ejecutó el harness nuevo y se versionó JSON.
- Señales reportadas:
  - `runtime_mode = fallback_no_api_key`,
  - `A_first_structural_diff = null`,
  - `B_first_structural_diff = null`,
  - `C_first_structural_diff.first_diff = executor_recent_dialogue_len`,
  - sin diferencias semánticas/expresivas observables en este entorno.

---

## 10) Riesgo de fix (estado actual)

No se aplicó fix de runtime en este ciclo, porque:
- falta evidencia semántica live para localizar con rigor el primer campo causal expresivo,
- un fix ahora sería prematuro y podría ser cosmético.

Siguiente experimento de mayor retorno:
- rerun del mismo script con `OPENAI_API_KEY` habilitada y misma batería A/B/C/D para fijar:
  1. primer diff semántico (`selected_memory` vs `planner_output.content_plan/turn_goal`),
  2. primer diff expresivo (`executor_output.spoken_text`),
  3. ablación mínima exacta sobre ese campo.
