# Extracción forense compacta — `forensics_humanity_progressive_intra_negotiation_run.json`

## 1) Naturaleza del artefacto

- **Archivo leído (completo):** `backend/docs/forensics_humanity_progressive_intra_negotiation_run.json`.
- **Script generador auditado:** `backend/scripts/forensics_humanity_progressive_intra_negotiation.py`.
- **Tipo de evidencia:** harness sintético con `TestClient` + parcheo de runtime:
  - usa `_fake_call_structured` (salidas de nodos simuladas),
  - usa `freeze_prompt_artifacts` parcheado para capturar payloads,
  - usa proxy heurístico de rigidez (`_rigidity_score`),
  - usa ablación artificial (`build_planner_input`/`build_executor_input` clamp a 4 turns).
- **Implicación metodológica:** evidencia estructural útil para hipótesis/causalidad experimental; **generalización a producción limitada**.

---

## 2) Hallazgos load-bearing (solo señal)

1. **Baseline continuo limpio no muestra divergencia inicial entre superficies.**
   - Evidencia: `checks.A_first_divergence = null`.
   - Confianza: alta (dentro del harness).
   - Dependencia del harness: media.

2. **Con residuo oculto solo en interfaz, la primera divergencia aparece en turno 1.**
   - Evidencia: `checks.C_first_divergence.turn_index = 1`, `first_diff = executor_recent_dialogue_len`.
   - Confianza: alta (medición directa en JSON).
   - Dependencia del harness: media-alta.

3. **La señal de rigidez aparece en turnos medios del escenario con residuo.**
   - Evidencia: `checks.C_positive_gap_turns = [3]`.
   - Confianza: media.
   - Dependencia del harness: alta (proxy `_rigidity_score` + textos del stub).

4. **La ablación (clamp de ventana) elimina la señal de rigidez positiva.**
   - Evidencia: `checks.D_positive_gap_turns = []`.
   - Confianza: media.
   - Dependencia del harness: alta (ablación y generación sintética).

5. **La divergencia estructural de ventana persiste incluso con ablación, pero ya no escala a “gap de rigidez”.**
   - Evidencia: `checks.D_first_divergence.first_diff = executor_recent_dialogue_len`, pero sin positive gaps.
   - Confianza: media.
   - Dependencia del harness: alta.

6. **Hay diferencia semántica puntual en `planner_output_turn_goal` en C, no en A ni en D.**
   - Evidencia: en C aparece diff de `planner_output_turn_goal` en turno 3 (comparación turno a turno).
   - Confianza: media.
   - Dependencia del harness: alta (planner synthetic policy).

7. **No hay prueba en este artefacto de un bug nuevo de runtime real per-surface.**
   - Evidencia: baseline A limpio sin divergencia; toda señal fuerte emerge bajo intervención sintética (residuo inyectado/ablación).
   - Confianza: media-alta.
   - Dependencia del harness: media.

---

## 3) Tabla corta por escenarios

| Escenario | first_divergence | first_turn_with_positive_gap | planner_recent_dialogue_len_diff | executor_recent_dialogue_len_diff | planner_output_turn_goal_diff | conclusión |
|---|---|---:|---|---|---|---|
| `A_baseline_continuous_clean` | `null` | `none` | none | none | none | sin divergencia estructural temprana |
| `C_progressive_hidden_residual_interfaz` | turno 1: `executor_recent_dialogue_len` | 3 | sí (desde t1: 1 vs 5) | sí (desde t1) | sí (t3) | residuo acumulativo induce deriva experimental |
| `D_ablation_clamp_recent_window` | turno 1: `executor_recent_dialogue_len` | `none` | sí (desde t1: 1 vs 4) | sí (desde t1) | none | al recortar ventana desaparece señal de rigidez |

---

## 4) Primer punto real de divergencia

- **Primer diff observado:** `executor_recent_dialogue_len`.
- **Escenario:** `C_progressive_hidden_residual_interfaz`.
- **Turno:** 1.
- **Tipo de evidencia:** estructural directa (longitud de ventana), no inferida.
- **¿Basta por sí solo para explicar rigidez?** No. Por sí solo muestra skew de contexto; la relación con tono se apoya en evidencia experimental posterior (`C_positive_gap_turns`, ablación D), no en causalidad de producción cerrada.

---

## 5) Separación explícita: evidencia estructural vs semántica

### Evidencia estructural (más robusta dentro del artefacto)
- `A_first_divergence = null`.
- `C_first_divergence = executor_recent_dialogue_len (t1)`.
- `D_first_divergence = executor_recent_dialogue_len (t1)`.
- Diferencias de ventana contextual en planner/executor desde primeros turnos en C y D.

### Evidencia semántica (más condicionada)
- `C_positive_gap_turns = [3]` depende de `_rigidity_score`.
- Texto de respuestas depende de `_fake_call_structured` (no modelo live).
- Diff de `planner_output_turn_goal` en C depende de regla sintética del planner en el harness.

---

## 6) Qué queda realmente demostrado

### Confirmado
- El artefacto demuestra que el patrón “residuo acumulativo -> skew de ventana -> señal de endurecimiento” **es reproducible experimentalmente**.
- El baseline limpio no enseña una divergencia temprana estructural entre superficies.

### Debilitado / no confirmado
- Que exista **ya** un bug nuevo de runtime real per-surface probado por este artefacto.
- Que la métrica de rigidez del harness equivalga 1:1 a degradación humana en producción.

### Abierto
- Validar el mismo patrón con ejecución live (sin `_fake_call_structured`) para confirmar causalidad en producción.
- Medir qué subcampo semántico real (p.ej. `selected_memory`, `memory_working.last_turn_summary`, `planner_output.content_plan`) cruza primero hacia formulación administrativa.

---

## Respuestas directas

- **¿El baseline limpio muestra divergencia real?** No; `A_first_divergence = null`.
- **¿Cuál es el primer diff en el escenario con residuo?** `executor_recent_dialogue_len` en turno 1.
- **¿En qué turnos aparece gap positivo de rigidez?** En C aparece en turno 3 (`[3]`); en D no aparece (`[]`).
- **¿La ablación elimina la señal?** Sí, elimina la señal positiva de rigidez en este harness.
- **¿Eso demuestra causalidad fuerte o solo causalidad experimental dentro del harness?** Causalidad experimental dentro del harness.
- **¿Se encontró un bug nuevo de runtime real o solo se acotó una hipótesis experimental?** Se acotó una hipótesis experimental; bug runtime nuevo no queda probado aquí.
- **¿Qué siguiente experimento sería el más rentable ahora?** Repetir A/C/D con llamadas live sin `_fake_call_structured` y score semántico de outputs/planner-content para fijar primer diff semántico real.
