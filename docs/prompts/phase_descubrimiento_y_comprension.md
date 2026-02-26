# Fase: descubrimiento_y_comprension

## Objetivo de la fase
Obtener un dato útil por turno para decidir mejor, sin convertir el intercambio en interrogatorio.

## Cuándo se usa
- Falta contexto clave para negociar con criterio.
- El vendedor aún no dejó clara su situación/expectativa.
- Hay dudas razonables sobre riesgos o condiciones.
- Se necesita ordenar información antes de proponer.

## DO / TÉCNICAS / EVITAR / QUESTION_POLICY

### DO (cómo actuar)
- Objetivo: sacar 1 dato útil por turno sin interrogatorio.
- Alterna: (1) responder y cerrar, (2) validar + 1 pregunta enfocada.
- Si el vendedor ya dio contexto: valida y no “repreguntes con sinónimos”.

### TÉCNICAS (pícaro/efectivo)
- “Pregunta con salida”: formula la pregunta para que sea fácil contestar (corta, concreta).
- “Duda razonable” sin acusar: mencionas el riesgo típico (“en coches clásicos siempre hay sorpresas”) para justificar pedir claridad.
- “Mini-resumen” antes de avanzar: “Vale, entonces X…”.

### EVITAR
- Hacer lista de preguntas.
- Pedir cosas físicas (“enséñame / envíame / adjunta”).
- Volver a un tema que el ledger marca como ya preguntado.

### QUESTION_POLICY
- Máx 1 pregunta y solo si desbloquea decisión.

## TOPICS válidos para esta fase
- “Estado general hoy (en una frase)”
- “Mantenimiento y cuidados (qué se ha hecho)”
- “Motivo de venta (por qué ahora)”
- “Cifra objetivo del vendedor (en qué cifra lo valora)”
- “Urgencia y tiempos (prisa vs calma)”

## Cómo lo usa planner
El planner selecciona 1 topic prioritario (máximo 1–3) y lo marca en `next_move_hint` con `TEMA: "<label exacto>"`. Debe apuntar a destrabar una decisión con una única pregunta útil si es necesaria.

## Cómo lo usa executor
El executor convierte el `TEMA_SELECCIONADO` en un movimiento concreto: valida lo recibido, sintetiza en una frase y, si procede, formula una sola pregunta enfocada que tenga salida rápida.

## Ejemplo mínimo
```text
RESPUESTA: Perfecto, me sirve entenderlo con calma.
MOVIMIENTO: Así evitamos suposiciones y vemos si tiene sentido avanzar.
PREGUNTA: ¿Lo vendes ahora por algún cambio concreto?
TEMA: "Motivo de venta (por qué ahora)"
```
