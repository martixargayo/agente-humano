# Forense profundo: degradación progresiva de humanidad en `interfaz_usuario` (planner/executor)

## 1) Resumen ejecutivo

Se investigó una degradación fina (rigidez administrativa) con foco en `planner -> executor` y en la hipótesis de **arrastre acumulativo**.

Conclusión principal:
- La deriva aparece de forma progresiva cuando `interfaz_usuario` reutiliza la misma sesión a través de episodios semánticamente nuevos.
- El primer punto visible de divergencia en el harness aparece en `executor_input.recent_dialogue_short.length` (misma familia de skew residual acumulativo), y después la realización se vuelve más rígida.
- El patrón no es “cerebro distinto”; en control simétrico (mismo patrón de uso) las superficies convergen.
- Se aplicó un fix mínimo y de bajo riesgo para cortar esa acumulación en el caso real más frecuente: **auto-reset de conversación en `interfaz_usuario` al detectar opener fresco tras fase terminal con historial acumulado**.

## 2) Hipótesis y foco

Hipótesis central: hay contaminación residual acumulativa que no rompe el pipeline pero endurece el estilo al avanzar turnos, especialmente en `interfaz_usuario` por patrón de uso (reutilización de sesión).

Foco técnico auditado:
- `planner_input`
- `planner_output`
- `executor_input`
- `executor_output`
- bootstrap/session handling en `interfaz_usuario`

## 3) Metodología

- Lectura estática de servicios de superficie y builders de orquestación.
- Harness nuevo reproducible con captura de payloads por nodo (via `freeze_prompt_artifacts`) y comparación A/B.
- Normalización de ruido efímero (`turn_id`, `timestamp_iso`).
- Escenarios:
  1. baseline fresco en ambas superficies,
  2. reutilización progresiva solo en interfaz vs fresh en optimizador,
  3. control de simetría (ambas superficies con mismo patrón de reuse),
  4. boundary/primer-turn tras fase terminal.

## 4) Evidencia

Artefacto: `backend/docs/forensics_humanity_residual_planner_executor_run.json`

Hallazgos:
- `both_fresh_per_episode`: paridad aceptable.
- `interfaz_reuse_vs_optimizer_fresh`: la primera divergencia aparece desde episodio 2 (`executor_recent_dialogue_len`), señal de acumulación de contexto residual.
- `both_reuse_control`: al forzar mismo patrón, la asimetría se reduce (apunta a patrón de uso + estado acumulado, no a cerebro distinto).
- `interfaz_boundary_auto_reset`: el auto-reset se activa y crea nueva sesión limpia, evitando arranque contaminado del nuevo episodio.

## 5) Primer punto de divergencia causal

`executor_input.recent_dialogue_short.length` en el escenario de reuse asimétrico (interfaz reuse, optimizador fresh).

## 6) Causalidad y no correlación

Se satisface criterio forense:
1. baseline sin skew asimétrico => sin divergencia fuerte,
2. skew acumulativo controlado por patrón de reuse => divergencia reproducible,
3. control simétrico de patrón => convergencia relativa,
4. fix de boundary reset => bloqueo de arranque contaminado entre episodios.

## 7) Fix implementado

Archivo: `backend/interfaz_usuario/services.py`

Cambio:
- nueva heurística `_should_auto_reset_for_fresh_opener(...)`.
- en `run_turn`, si no se pide explícitamente `new_conversation` pero llega un opener fresco (`hola`, `buenas`, etc.) tras fase terminal (`formalizacion_del_acuerdo` o `abandono`) y con historial acumulado, se crea automáticamente nueva conversación limpia.

Modelo/API:
- `backend/interfaz_usuario/models.py`: se añade `auto_reset_applied: bool` en la respuesta para observabilidad del comportamiento.

## 8) Validación

- Script: `backend/scripts/forensics_humanity_residual_planner_executor.py`.
- Tests:
  - `backend/tests/test_humanity_residual_planner_executor_forensics.py`
  - `backend/tests/test_interfaz_usuario_api.py` (nuevo caso de auto reset boundary)

## 9) Riesgos

- Bajo: el reset solo se activa con combinación específica (fase terminal + historial + opener fresco).
- Riesgo funcional: algunos usuarios pueden querer continuar la misma negociación con “hola”; en ese caso pueden desactivar usando flujo explícito (no opener) o ajustar criterio en iteración futura.

## 10) Estado final

- Se confirma la hipótesis de **degradación progresiva por residuo acumulativo** en patrón de uso asimétrico.
- Se aplica fix conservador en punto operativo de mayor impacto real sin tocar prompts/modelos.
