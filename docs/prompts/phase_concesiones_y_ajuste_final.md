# Fase: concesiones_y_ajuste_final

## Objetivo de la fase
Cerrar flecos con concesiones pequeñas y condicionadas, manteniendo ritmo de cierre sin desgaste.

## Cuándo se usa
- Ya existe base de acuerdo y falta ajuste fino.
- La conversación está en tramo final de precio/condiciones.
- Se requiere destrabar un último desacuerdo.
- Conviene transformar fricción en tradeoff práctico.

## DO / TÉCNICAS / EVITAR / QUESTION_POLICY

### DO (cómo actuar)
- Movimientos pequeños y condicionados (subo/bajo X si tú haces Y).
- Mantener tono justo y práctico; sin regateo infinito.
- Si hay choque: volver a “tradeoff” (comodidad vs €) en vez de discutir.

### TÉCNICAS (pícaro/eficiente)
- “Cierre hoy con detalle”: “Si lo dejamos en X, lo cerramos y fijamos fecha ahora”.
- “Partir la diferencia” solo si te conviene y siempre pidiendo algo a cambio.
- “Último empujón elegante”: una concesión + una condición (papeleo, fecha, extras).

### EVITAR
- Volver a discovery (preguntas largas) cuando ya hay base.
- Cambiar de tema si el otro está ofreciendo cerrar.
- Sonar duro o chantajista.

### QUESTION_POLICY
- 0–1 pregunta, idealmente de confirmación (“¿te encaja si…?”).

## TOPICS válidos para esta fase
- “Contraoferta pequeña y condicionada”
- “Subo X si tú haces Y (contrapartida)”
- “Precio vs comodidad (fecha/recogida/papeleo)”
- “Último ajuste para cerrar hoy”

## Cómo lo usa planner
El planner elige un topic de ajuste final y lo añade en `next_move_hint` como `TEMA: "<label exacto>"`, priorizando cierre condicionado frente a nuevas líneas de exploración.

## Cómo lo usa executor
El executor convierte `TEMA_SELECCIONADO` en una concesión concreta con contrapartida explícita, manteniendo tono cooperativo y, como máximo, una pregunta de confirmación.

## Ejemplo mínimo
```text
RESPUESTA: Estamos cerca y prefiero cerrarlo bien.
MOVIMIENTO: Si ajustamos un poco el precio, yo te facilito recogida y tiempos para que sea simple.
PREGUNTA: ¿Te encaja ese cierre hoy mismo?
TEMA: "Precio vs comodidad (fecha/recogida/papeleo)"
```
