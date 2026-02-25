# Flujo operativo: pregunta “¿por qué lo vendes?” con Judge Scribe + Semantic Ledger

## 1) Inicio del turno: planner guía y executor pregunta

- El executor puede preguntar: **“¿Por qué lo vendes?”**.
- Esa pregunta sale del planner cuando está en fase de **descubrimiento** y sugiere un `next_move_hint` como “explorar motivo de venta”.
- La pregunta no nace de una regla dura, sino de la orientación semántica de fase + estilo + hint.

## 2) Judge scribe: en el mismo turno deja apuntado lo ocurrido

Después de ver:
- qué preguntó el agente,
- qué respondió el usuario,

el judge actualiza el `semantic_ledger`.

### 2.1 Siempre registra que ya se preguntó

`lo_que_ya_pregunte`:
- “Pregunté el motivo de la venta.”

### 2.2 Si el usuario respondió algo útil

`lo_que_ya_se_toco`:
- “Motivo de venta: ya no lo necesita / quiere venderlo ahora.”

### 2.3 Si el usuario fue vago o esquivó

`lo_que_falta_pero_no_insistire`:
- “Motivo exacto de venta no quedó claro; no insistir.”

## 3) Progress updater persiste el ledger

- El `progress_updater` guarda las tres listas del `semantic_ledger` en `progress_state`.
- Desde ese momento, la nota viaja a los turnos siguientes como memoria operativa.

## 4) Planner lee ledger y evita repetir por diseño semántico

En el prompt del planner, el ledger entra como memoria de trabajo.

Instrucciones semánticas clave del planner:
- “No vuelvas a preguntar cosas que ya estén en `lo_que_ya_pregunte`.”
- “Si está en `lo_que_falta_pero_no_insistire`, no lo persigas: pivota a otro ángulo.”

Resultado esperado en el siguiente turno:
- en vez de repetir “¿por qué lo vendes?”,
- el planner sugiere otra línea no repetida (precio, condiciones, proceso),
- o validación breve y espacio conversacional.

## 5) Si el usuario vuelve al tema por su cuenta

- El executor responde/valida de forma natural.
- No hace falta volver a preguntar.
- El judge puede reforzar o mover esa información a `lo_que_ya_se_toco`.

## 6) Qué NO hace este sistema (por diseño)

- No hay `if topic_asked then forbid()` por código.
- No hay matching por keywords.
- No hay gates rígidos.

El “no repetir” ocurre porque:
1. El judge lo deja explícito en lenguaje natural (“ya pregunté X”).
2. El planner lo interpreta semánticamente y evita insistir.
3. El executor mantiene ese estilo y, si reaparece, valida sin reabrir el interrogatorio.

## 7) Mejora recomendada para robustez semántica (sin reglas duras)

Cuando algo ya se preguntó y no se debe reabrir, usar redacción muy explícita en ledger, por ejemplo:

- “NO volver a preguntar el motivo de la venta.”

Cuanto más explícita la nota semántica, más consistente será el comportamiento del planner sin necesidad de añadir heurísticas o lógica determinista.
