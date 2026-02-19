# Repertorio de policies (v1) para `phase_policy_planner`
## ~15 inspirations operativas (no recetas literales)

> Este catálogo es una guía de patterns para el planner LLM-first. No es un motor de ejecución literal.

---

## 1) `safe_neutral_core`
- **Cuándo usar**: contexto ambiguo o inicio sin señales fuertes.
- **Objetivo**: mantener avance conversacional sin riesgos.
- **Movimiento típico**: resumir + pregunta breve de clarificación.
- **Evitar**: sobre-preguntar o cerrar prematuramente.
- **Señal de éxito**: aparece información nueva verificable.

## 2) `deescalate_tension`
- **Cuándo usar**: tensión media/alta, fricción creciente.
- **Objetivo**: bajar activación emocional.
- **Movimiento típico**: validar emoción + reconducir con foco concreto.
- **Evitar**: tono paternalista o confrontativo.
- **Señal de éxito**: respuesta menos agresiva y más cooperativa.

## 3) `boundary_and_respect`
- **Cuándo usar**: faltas de respeto, amenazas, límites difusos.
- **Objetivo**: proteger marco seguro.
- **Movimiento típico**: límite claro + invitación a seguir en términos respetuosos.
- **Evitar**: ultimátum innecesario.
- **Señal de éxito**: restablecimiento de canal.

## 4) `clarify_missing_info`
- **Cuándo usar**: propuesta vaga o términos incompletos.
- **Objetivo**: convertir ambigüedad en datos operativos.
- **Movimiento típico**: 1–2 preguntas específicas.
- **Evitar**: preguntas redundantes.
- **Señal de éxito**: variables críticas completadas.

## 5) `info_extract_critical`
- **Cuándo usar**: hay claim relevante sin soporte.
- **Objetivo**: obtener información verificable de alto impacto.
- **Movimiento típico**: pedir detalle concreto (condiciones, plazos, evidencias).
- **Evitar**: aceptar claim por defecto.
- **Señal de éxito**: datos que cambian decisión.

## 6) `discover_interests_open`
- **Cuándo usar**: hay posiciones pero no intereses.
- **Objetivo**: descubrir motivaciones reales.
- **Movimiento típico**: pregunta abierta orientada a prioridad.
- **Evitar**: discutir precio demasiado pronto.
- **Señal de éxito**: interés principal explícito.

## 7) `time_pressure_probe`
- **Cuándo usar**: deadline declarado.
- **Objetivo**: validar urgencia real vs táctica.
- **Movimiento típico**: preguntar fecha exacta y consecuencias del plazo.
- **Evitar**: ceder por presión no verificada.
- **Señal de éxito**: deadline trazable y creíble.

## 8) `credibility_probe`
- **Cuándo usar**: oferta externa/claim de apalancamiento.
- **Objetivo**: verificar credibilidad.
- **Movimiento típico**: solicitar términos verificables.
- **Evitar**: acusación frontal sin base.
- **Señal de éxito**: evidencia o retractación.

## 9) `tradeoff_if_then`
- **Cuándo usar**: hay concesiones condicionales posibles.
- **Objetivo**: construir intercambio explícito y equilibrado.
- **Movimiento típico**: “si X, entonces Y” concreto.
- **Evitar**: concesión unilateral.
- **Señal de éxito**: reciprocidad aceptable.

## 10) `package_option_builder`
- **Cuándo usar**: múltiples variables negociables.
- **Objetivo**: crear 2–3 paquetes comparables.
- **Movimiento típico**: presentar opciones con pros/cons.
- **Evitar**: exceso de complejidad.
- **Señal de éxito**: preferencia clara por una opción.

## 11) `objection_handler`
- **Cuándo usar**: objeción concreta bloquea avance.
- **Objetivo**: resolver bloqueo sin escalar.
- **Movimiento típico**: reconocer objeción + propuesta de ajuste.
- **Evitar**: invalidar la objeción del otro.
- **Señal de éxito**: objeción transformada en condición negociable.

## 12) `anchor_reframe_soft`
- **Cuándo usar**: ancla dura de precio/condición.
- **Objetivo**: reencuadrar criterios sin choque directo.
- **Movimiento típico**: mover conversación a valor/condiciones.
- **Evitar**: contra-ancla agresiva temprana.
- **Señal de éxito**: conversación sale de la cifra fija.

## 13) `micro_commitment_next_step`
- **Cuándo usar**: hay avance parcial.
- **Objetivo**: cerrar siguiente paso verificable.
- **Movimiento típico**: pedir mini-compromiso temporal/operativo.
- **Evitar**: empujar cierre total antes de tiempo.
- **Señal de éxito**: próximo paso acordado.

## 14) `formalize_recap_confirm`
- **Cuándo usar**: convergencia alta.
- **Objetivo**: confirmar términos y evitar malentendidos.
- **Movimiento típico**: recap breve + confirmación explícita.
- **Evitar**: omitir detalles críticos.
- **Señal de éxito**: confirmación clara de términos.

## 15) `close_graciously`
- **Cuándo usar**: cierre positivo o no-acuerdo respetuoso.
- **Objetivo**: cerrar sin quemar relación.
- **Movimiento típico**: resumen final + puerta abierta.
- **Evitar**: cierre frío/abrupto.
- **Señal de éxito**: salida ordenada y reputación intacta.

---

## Reglas de uso por parte del planner

1. Elegir 1–3 inspirations por turno con `fit_reason`.
2. Diseñar plan libremente (no plantillas rígidas).
3. Mantener coherencia con `active_plan` y judgement previo.
4. Priorizar seguridad cuando `recovery_mode=true`.
