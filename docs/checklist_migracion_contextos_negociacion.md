# Checklist de migración segura a `contextos` para `negociacion`

## Objetivo

Usar esta checklist como guía de corte por fase para evitar que la migración cambie comportamiento funcional del caso actual.

---

## A. Checklist de invariantes funcionales

- [ ] El orden del pipeline sigue siendo memory -> phase_classifier -> planner -> executor.
- [ ] `NegotiationTurnConfig` mantiene mismos modelos, límites y flags para el contexto baseline.
- [ ] El bundle baseline usa exactamente los mismos prompts efectivos que hoy.
- [ ] `persona.json` y `negotiation_brief.json` del baseline son equivalentes a los actuales.
- [ ] `phase_cards.json` y `phase_classifier_card.json` del baseline son equivalentes a los actuales.
- [ ] El shape de `CanonicalState` no cambia.
- [ ] El shape de `NegotiationState` no cambia.
- [ ] `NegotiationPhase` no cambia.
- [ ] `finish_button_armed` sigue dependiendo de la misma lógica actual.
- [ ] La UI existente sigue pudiendo arrancar el contexto baseline sin pasos extra obligatorios.
- [ ] El endpoint actual de turn sigue funcionando para el baseline.
- [ ] El feedback actual sigue pudiendo generarse para el baseline.
- [ ] El optimizer sigue pudiendo usar el baseline aunque todavía no elija explícitamente otro contexto.

---

## B. Checklist de contexto oficial

- [ ] Existe una raíz oficial para contextos de `negociacion`.
- [ ] Existe un contexto baseline equivalente al caso actual.
- [ ] Existe un descriptor mínimo (`context_id`, `flow_id`, `context_version`, `public_slug`).
- [ ] Runtime y canonical state resuelven el mismo contexto efectivo.
- [ ] No quedan dos fuentes de verdad funcionales sin documentación clara.

---

## C. Checklist de sesión y aislamiento

- [ ] Toda sesión nueva de `negociacion` queda ligada a un `context_id`.
- [ ] `new_conversation` hereda `context_id`.
- [ ] El backend no permite mezclar silenciosamente un contexto nuevo con una sesión antigua incompatible.
- [ ] La identidad contextual sobrevive durante toda la conversación.
- [ ] La identidad contextual también existe en sandbox del optimizer.

---

## D. Checklist de trazas y diagnósticos

- [ ] Cada turno deja visible `context_id`.
- [ ] Cada turno deja visible `context_version` o hash equivalente.
- [ ] Se puede distinguir baseline oficial vs contexto con overrides.
- [ ] Las comparaciones del optimizer no mezclan contextos sin indicarlo.

---

## E. Checklist de evaluación

- [ ] El bundle de evaluación sabe qué `context_id` se está evaluando.
- [ ] Los prompts de evaluación del baseline siguen siendo equivalentes a los actuales.
- [ ] La rúbrica baseline sigue siendo equivalente a la actual.
- [ ] Job/report/provenance guardan identidad contextual.
- [ ] El formato general del informe no cambia.

---

## F. Checklist de entrada pública

- [ ] La URL o entrada pública resuelve contexto de forma consistente.
- [ ] El backend es la fuente de verdad de `URL/slug -> context_id`.
- [ ] El baseline actual sigue accesible sin romper la entrada existente.
- [ ] No existe mutación silenciosa de contexto al refrescar o abrir otra pestaña.

---

## G. Gate de salida antes de crear un segundo contexto

No debería crearse un segundo contexto oficial hasta que se cumpla todo esto:

- [ ] baseline oficial resuelto por contexto
- [ ] `context_id` fijado en sesión
- [ ] trazas context-aware
- [ ] evaluación context-aware mínima
- [ ] optimizer context-aware mínimo
- [ ] smoke checks del baseline sin regresión funcional visible
