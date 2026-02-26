# Phase System Overview (planner → executor)

## Objetivo
Documentar, en formato runtime-friendly, cómo se conectan `PHASES_RESUMEN`, `TOPICS_POR_FASE`, `next_move_hint` y `PHASE_CARD_EXTENDIDA` para asegurar progreso por turno sin drift.

## Componentes y propósito

### 1) PHASES_RESUMEN (planner)
Sirve como mapa táctico corto (1 línea por fase) para elegir fase estable según contexto y `allowed_next_phases`.

Fases oficiales (IDs exactos):
- `clima_humano`: crear cordialidad real y confianza (inicio o si hay tensión); cero presión y casi sin preguntas.
- `descubrimiento_y_comprension`: entender contexto, motivaciones y variables clave (cuando falta info para negociar); preguntas suaves y puntuales.
- `propuesta_creativa`: desbloquear con opciones/trueques (cuando hay incertidumbre o distancia en precio); 1–2 propuestas concretas.
- `concesiones_y_ajuste_final`: ajustar flecos con concesiones pequeñas y condicionadas (cuando ya hay base); cerrar sin desgaste.
- `formalizacion_del_acuerdo`: confirmar lo acordado como checklist (cuando ya hay “hecho/vale”); cero regateo.

Regla de uso en planner:
- Elegir `phase` **solo** dentro de `allowed_next_phases`.
- Evitar saltos bruscos; mantener fase o avanzar un paso lógico.

### 2) TOPICS_POR_FASE (planner)
Es un menú de temas con labels cortos y estables para guiar el foco del turno y mantener progreso sin interrogatorio.

Regla de selección:
- Ideal: seleccionar 1 topic por turno.
- Máximo: 1–3 topics por turno.
- Los labels deben usarse **EXACTAMENTE** como están escritos (consistencia y parseo).

### 3) PHASE_CARD_EXTENDIDA (executor)
Instrucción expandida por fase para ejecutar sin drift:
- DO (cómo actuar)
- TÉCNICAS
- EVITAR
- QUESTION_POLICY
- TEMA_SELECCIONADO

Regla runtime:
- Se hace lookup por `phase` y se inyecta **solo una** tarjeta (no el mapa completo).

### 4) TEMA_SELECCIONADO
Foco táctico del turno. Debe ser un label válido de `TOPICS_POR_FASE` para la fase actual.

Cómo se transmite al executor:
- Opción 1 (preferida sin cambiar schemas): incluirlo dentro de `next_move_hint` como línea:
  - `TEMA: "<label exacto>"`
- Opción 2 (si runtime ya lo soporta): `topic_selected` separado en input del executor.

Regla de ejecución:
- El executor usa `TEMA_SELECCIONADO` como ancla del `MOVIMIENTO` del turno, sin convertir la salida en interrogatorio.

### 5) Política de preguntas
- Planner: `next_move_hint` con máximo 1 pregunta.
- Executor: respeta `QUESTION_POLICY` de la fase y `max_questions` del input.

## TOPICS_POR_FASE (fuente operativa)

### clima_humano
- “Pequeño rapport: día / cómo está”
- “Historia ligera: ¿hace cuánto lo tienes?”
- “Anécdota/valor emocional (sin negociar)”

### descubrimiento_y_comprension
- “Estado general hoy (en una frase)”
- “Mantenimiento y cuidados (qué se ha hecho)”
- “Motivo de venta (por qué ahora)”
- “Cifra objetivo del vendedor (en qué cifra lo valora)”
- “Urgencia y tiempos (prisa vs calma)”

### propuesta_creativa
- “Cierre rápido condicionado (si encaja, cerramos ya)”
- “Papeleo y trámites (quién se encarga)”
- “Señal + fecha de pago (todo registrado)”
- “Incluye extras/recambios/herramientas”
- “Reparto de costes (gestoría/transferencia/transporte)”

### concesiones_y_ajuste_final
- “Contraoferta pequeña y condicionada”
- “Subo X si tú haces Y (contrapartida)”
- “Precio vs comodidad (fecha/recogida/papeleo)”
- “Último ajuste para cerrar hoy”

### formalizacion_del_acuerdo
- “Checklist: precio + qué incluye”
- “Checklist: forma y fecha de pago”
- “Checklist: entrega y trámites”
- “Confirmación final (¿queda así?)”

## Formato recomendado en `next_move_hint`

```text
RESPUESTA: ...
MOVIMIENTO: ...
PREGUNTA: ...
TEMA: "<label exacto de TOPICS_POR_FASE>"
```

## Diagrama textual (runtime)

```text
planner_llm
  └─> planner_semantic_output
       ├─ phase
       ├─ next_move_hint (incluye: TEMA: "...")
       └─ what_not_to_repeat
             |
             v
runtime
  └─ lookup PHASE_CARD_EXTENDIDA por phase (solo 1)
             |
             v
executor_llm
  └─ usa phase + next_move_hint + TEMA + PHASE_CARD_EXTENDIDA
      para redactar respuesta final sin drift
```
