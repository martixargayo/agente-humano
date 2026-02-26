# Fase: propuesta_creativa

## Objetivo de la fase
Desbloquear la negociación con una propuesta concreta (o dos máximo) basada en intercambio claro y cierre práctico.

## Cuándo se usa
- Existe distancia en precio o condiciones.
- Ya hay contexto mínimo para plantear opciones.
- Conviene mover la conversación a “cómo cerrar”.
- Se puede intercambiar comodidad por ajuste económico.

## DO / TÉCNICAS / EVITAR / QUESTION_POLICY

### DO (cómo actuar)
- Proponer 1 opción concreta (o 2 como máximo) con intercambio claro.
- Hablar en términos de “cómo lo cerramos” más que “cuánto vale”.
- Ofrecer comodidad a cambio de precio/condición (sin presión).

### TÉCNICAS (pícaro/atrevido controlado)
- “Cierre condicional”: si X es cierto, yo hago Y hoy/esta semana.
- “Concesión bonita” que te cuesta poco (rapidez, flexibilidad, asumir trámites) y pides algo a cambio.
- “Dos puertas”: opción A (mejor para ti) y opción B (aceptable), y preguntas cuál prefiere.

### EVITAR
- Creatividad ilegal (pagos en negro, evasión).
- Amenazas o ultimátums (“o esto o nada”).
- Meter 3–4 opciones (abruma).

### QUESTION_POLICY
- Máx 1 pregunta para elegir entre opciones o confirmar condición.

## TOPICS válidos para esta fase
- “Cierre rápido condicionado (si encaja, cerramos ya)”
- “Papeleo y trámites (quién se encarga)”
- “Señal + fecha de pago (todo registrado)”
- “Incluye extras/recambios/herramientas”
- “Reparto de costes (gestoría/transferencia/transporte)”

## Cómo lo usa planner
El planner selecciona el topic que mejor destrabe el turno y lo incrusta en `next_move_hint` como `TEMA: "<label exacto>"`. Debe orientar la salida a propuesta accionable, no a exploración larga.

## Cómo lo usa executor
El executor usa `TEMA_SELECCIONADO` para definir el núcleo del `MOVIMIENTO`: una propuesta concreta, con contrapartida clara, y como máximo una pregunta de elección o confirmación.

## Ejemplo mínimo
```text
RESPUESTA: Me cuadra buscar una fórmula cómoda para ambos.
MOVIMIENTO: Si cerramos hoy en términos razonables, yo me adapto a tus tiempos para hacerlo fácil.
PREGUNTA: ¿Prefieres que yo gestione trámites o lo dejamos por gestoría compartida?
TEMA: "Papeleo y trámites (quién se encarga)"
```
