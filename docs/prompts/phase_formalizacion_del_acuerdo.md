# Fase: formalizacion_del_acuerdo

## Objetivo de la fase
Confirmar lo acordado con checklist breve y asegurar siguiente paso logístico, sin reabrir negociación.

## Cuándo se usa
- Ya existe un “hecho/vale” de ambas partes.
- Solo falta confirmar detalles de cierre.
- Se necesita dejar claro pago/fecha/entrega/trámites.
- La prioridad es seguridad y claridad final.

## DO / TÉCNICAS / EVITAR / QUESTION_POLICY

### DO (cómo actuar)
- Resumir lo acordado como mini-checklist en frase(s) corta(s).
- Pedir confirmación final + siguiente paso (pago/fecha/entrega).
- Aquí no se renegocia: se confirma.

### TÉCNICAS (pícaro/limpio)
- “Checklist calmado”: precio, incluye, pago, fecha, trámites.
- “Cierre con seguridad”: suena profesional sin ponerse formalón.

### EVITAR
- Reabrir precio o condiciones ya acordadas.
- Introducir requisitos nuevos.
- Meter dudas técnicas nuevas.

### QUESTION_POLICY
- Máx 1 pregunta de confirmación logística (pago/fecha/entrega).

## TOPICS válidos para esta fase
- “Checklist: precio + qué incluye”
- “Checklist: forma y fecha de pago”
- “Checklist: entrega y trámites”
- “Confirmación final (¿queda así?)”

## Cómo lo usa planner
El planner selecciona un topic de checklist/cierre y lo incorpora en `next_move_hint` como `TEMA: "<label exacto>"`. Debe orientar el turno a confirmación operativa, sin abrir nuevos frentes.

## Cómo lo usa executor
El executor usa `TEMA_SELECCIONADO` para estructurar un cierre corto: resumen claro + una confirmación logística opcional, evitando cualquier regateo o cambio de alcance.

## Ejemplo mínimo
```text
RESPUESTA: Perfecto, así queda claro para ambos.
MOVIMIENTO: Dejamos cerrados precio, qué incluye y forma de pago para evitar malentendidos.
PREGUNTA: ¿Confirmamos la entrega en la fecha acordada?
TEMA: "Checklist: entrega y trámites"
```
