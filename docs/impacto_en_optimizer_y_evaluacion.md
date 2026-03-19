# Impacto del modelo `context pack` en optimizer y evaluación

## Resumen

Si se adopta el enfoque de `context packs`, las dos piezas que más necesitan disciplina adicional son:

- el **optimizer**, porque hoy trabaja por overrides y no por identidad oficial de contexto;
- la **evaluación**, porque hoy es de dominio `negociacion` pero no de contexto concreto.

La buena noticia es que ambas piezas **pueden encajar bien** con la estrategia propuesta. La mala es que **no basta con cambiar archivos**: necesitan trazabilidad explícita del contexto.

---

# A. Optimizer

## A.1. ¿Bastaría con elegir `context_id`?

**Como modelo objetivo, sí; en el estado actual, no del todo.**

Elegir `context_id` debería ser la base correcta porque permite decir:

- qué pack oficial estoy usando,
- qué URL pública estoy simulando,
- qué evaluación corresponde,
- y qué trazas son comparables entre sí.

Pero en el repo actual el optimizer no opera así. Opera con:

- sesiones espejo o sandbox,
- overrides por categoría (`prompt`, `config`, `contextual`),
- bundle temporal generado en `apply_overrides()`.

### Conclusión

`context_id` **debería convertirse en la identidad primaria**, pero seguirían existiendo overrides como capa secundaria de experimentación.

---

## A.2. Qué tendría que quedar fijado en sesión

Para que el optimizer sea robusto bajo este modelo, la sesión sandbox debería fijar al menos:

- `flow_id = negociacion`
- `context_id`
- `context_version` o hash del pack
- origen de la sesión (pública, clonado sandbox, nueva conversación)
- `source_user_id` / `source_session_id` si es copia
- `source_conversation_id` si aplica
- `preferred_conversation_id` si el sandbox se deriva de una conversación concreta

### Por qué importa

Porque hoy `optimizador_sandbox_meta` describe estrategia de clonado, pero no la identidad formal del contexto base. Sin eso, el sandbox puede ser correcto técnicamente pero ambiguo semánticamente.

---

## A.3. Qué trazas deberían incluir el contexto

Las trazas deberían incluir de forma explícita:

- `flow_name`
- `context_id`
- `context_version` o `context_pack_hash`
- si el turno usa pack oficial o pack con overrides
- lista/hashes de overrides aplicados
- idealmente la URL o slug público simulado

### Por qué es clave

Hoy las trazas ya son ricas en prompts, schemas, modelos, guardrails y threading. Añadir identidad de contexto haría que el optimizer pudiera comparar no solo “qué prompt cambió”, sino “qué contexto base estaba activo”.

---

## A.4. Qué riesgos de mezcla habría

Los riesgos principales en optimizer son:

1. comparar turns de contextos distintos como si fueran del mismo experimento;
2. clonar una sesión de un contexto y ejecutar un sandbox con otro sin reset claro;
3. usar un override sobre un bundle que no corresponde al caso que se cree estar probando;
4. guardar datasets/regresiones sin etiqueta de contexto;
5. interpretar resultados del optimizer como equivalentes a la URL pública cuando en realidad no comparten el mismo pack base.

---

## A.5. Qué papel tendría el optimizer en esta arquitectura

Debería tener tres roles concretos y acotados:

### 1. Selector de contexto base

Poder decir: “quiero probar `negociacion/mustang`”.

### 2. Simulador fiel del runtime público

Poder correr el mismo motor y el mismo contexto que usaría la URL pública.

### 3. Capa de experimentación diferencial

Poder añadir encima:

- cambios en prompts,
- cambios en assets,
- cambios en config,
- y comparar contra el baseline del mismo contexto.

### Lectura recomendada

El optimizer no debería ser “otro sistema de negociación”. Debería ser un **banco de pruebas del mismo flow/contexto**.

---

## A.6. Qué significa “ver trazas como si probara la URL pública”

Para que eso sea verdad, deberían coincidir:

- mismo `context_id`;
- mismo bundle base;
- mismo shape de sesión;
- misma política de conversación/threading;
- mismas reglas de evaluación y finalización;
- misma surface contract salvo los metadatos específicos del sandbox.

Si no coinciden esas piezas, el optimizer sigue siendo útil, pero ya no está probando exactamente la experiencia pública.

---

# B. Evaluación

## B.1. ¿Bastaría con prompts/rúbrica por contexto?

**En gran parte sí, pero no completamente.**

Es la capa más importante:

- prompt core por contexto,
- prompt trajectory por contexto,
- rúbrica por contexto.

Eso ya cubriría una gran parte de la adaptación semántica. Pero para que sea consistente también hace falta que el input bundle de evaluación sepa **qué contexto está evaluando**.

---

## B.2. Dependencias actuales de la evaluación

La evaluación actual depende de:

- `state.history` para reconstruir turnos;
- `world_state["negotiation_canonical"]` para `final_phase` y `finish_button_was_armed`;
- trazas para contar eventos de guardrails;
- prompts globales en `backend/evaluacion/prompts/`;
- una rúbrica global de dominio en `backend/evaluacion/domains/negotiation/rubrics/negotiation_rubric_v1.json`.

### Qué significa esto

La evaluación está razonablemente desacoplada del runtime, pero **todavía no resuelve contexto/caso**. Trabaja sobre “una conversación de negociación”, no sobre “una conversación del contexto `proveedor`”.

---

## B.3. Qué parte del pipeline de evaluación seguiría igual

Seguiría siendo útil y estable:

- la creación del job asíncrono;
- el pipeline `bundle -> core/trajectory -> reconciliation -> report`;
- el storage de jobs/reportes;
- la UI de polling y consumo del informe;
- la lógica base de validación de outputs;
- la existencia de un extractor de dominio negociación.

Esto es importante: la estrategia de `context packs` no obliga a rehacer el pipeline de evaluación.

---

## B.4. Qué parte dependería del contexto

Debería depender del contexto:

- prompt core;
- prompt trajectory, si el caso cambia la lectura de trayectoria;
- rúbrica;
- fixtures/dev bundles del caso;
- quizá parte del shaping si el caso necesita facts contextuales explícitos;
- metadatos del informe para decir qué contexto se evaluó.

---

## B.5. Riesgos específicos de evaluación si no se contextualiza bien

### Riesgo 1: rúbrica equivocada

Una conversación puede parecer razonable bajo una rúbrica general y ser mala bajo la lógica específica del caso.

### Riesgo 2: falsa comparabilidad

Dos informes de contextos distintos podrían parecer comparables cuando en realidad usan criterios distintos.

### Riesgo 3: feedback correcto formalmente, incorrecto pedagógicamente

El JSON puede ser válido y consistente, pero dar recomendaciones inadecuadas para ese caso concreto.

### Riesgo 4: desalineación con la URL pública

Si la actividad pública es `salario` y la evaluación sigue usando la rúbrica general o la de `mustang`, el usuario percibirá incoherencia entre simulación y feedback.

---

## B.6. Recomendación para evaluación bajo este modelo

La forma más sólida es pensar la evaluación así:

### Parte estable del sistema

- job lifecycle;
- assembly del reporte;
- validadores estructurales;
- transporte API/UI.

### Parte dependiente del contexto

- prompts evaluativos;
- rúbrica;
- fixtures/datasets;
- metadatos de contexto en el bundle;
- y, si hiciera falta, reglas de shaping específicas del contexto.

### Regla mínima imprescindible

Toda evaluación debe saber y persistir:

- `flow_id`
- `context_id`
- `context_version`

Sin eso, la contextualización será frágil.

---

# C. Recomendación conjunta

## Síntesis

La propuesta es buena si se formaliza así:

- **URL pública** resuelve `context_id`.
- **Sesión** queda fijada a `context_id`.
- **Runtime** carga el pack de ese contexto.
- **Optimizer** simula ese mismo contexto base y opcionalmente lo sobreescribe con overrides.
- **Evaluación** usa prompts/rúbrica del mismo contexto y deja trazabilidad explícita.

## Veredicto específico

### Optimizer

**Sí encaja**, pero no basta con elegir contexto “de palabra”; debe quedar persistido en sesión y trazas.

### Evaluación

**Sí encaja**, y aquí la propuesta es especialmente buena, siempre que el bundle de evaluación sea context-aware y no solo prompt-aware.

---

# D. Conclusión final

Bajo el modelo `context pack`, optimizer y evaluación no son un problema irresoluble. De hecho, ambos se benefician de una identidad contextual clara.

La clave arquitectónica es esta:

> el contexto no debe ser solo una carpeta de archivos; debe ser también una identidad explícita que viaje con la sesión, las trazas, los jobs de evaluación y las simulaciones del optimizer.

Si eso se respeta, el modelo sigue siendo simple y gana mucha solidez.
