# Análisis de viabilidad: `context packs` para `negociacion`

## Resumen ejecutivo

La hipótesis es **viable, pero solo de forma parcial y con fronteras muy concretas**.

Mirando el repositorio real, el flujo de `negociacion` ya está bastante cerca de un modelo de **motor estable + bundle de prompts/contexto**:

- el pipeline se construye desde una sola `NegotiationTurnConfig` con un único `prompts_dir`;
- los prompts del flujo ya se cargan desde disco por ruta;
- `persona.json`, `negotiation_brief.json`, `phase_cards.json` y `phase_classifier_card.json` ya se resuelven desde archivos fijos del bundle;
- el optimizer ya sabe clonar temporalmente un bundle de prompts y parte del contexto;
- la evaluación ya está separada del runtime conversacional y usa prompts/rúbrica propios.

Pero la simplificación propuesta **no describe todo el sistema actual**. Hay piezas del runtime que siguen acopladas al caso actual de una negociación de compraventa y que no se dejan variar solo con “cambiar `.txt` + `.json`”. Los principales límites son:

1. el **shape del estado canónico** (`NegotiationState`, `PlannerState`, `SceneState`, `NegotiationUiState`) es común y fijo;
2. el **phase system** usa un enum cerrado y una semántica concreta de fases;
3. la **evaluación** hoy es de dominio `negociacion`, pero no de caso/contexto;
4. la **UI pública** no resuelve todavía contexto desde URL ni fija ese contexto en sesión;
5. el **optimizer** solo soporta overrides parciales de contexto y no un `context_id` canónico;
6. hay heurísticas y contratos que, aunque reutilizables, están afinados al caso actual.

En consecuencia, la hipótesis fuerte:

> “dentro del flujo actual de negociación, lo que cambia entre casos puede modelarse principalmente como un cambio de prompts y JSONs fijos de contexto, sin necesidad de cambiar el motor”

es **verdadera para variantes del mismo tipo de negociación**, pero **deja de ser completamente cierta** cuando cambia alguna de estas dimensiones:

- el mapa de ejes negociables;
- la semántica de fases;
- la información estructural que el estado debe recordar;
- la semántica de cierre/UI;
- o los criterios de evaluación del caso.

La conclusión práctica es:

- **sí** conviene pensar `negociacion` como un motor estable;
- **sí** conviene encapsular por contexto los prompts, assets JSON y evaluación;
- **no** conviene asumir que eso elimina todos los acoplamientos;
- **sí** conviene fijar explícitamente qué significa “mismo flujo” para no forzar casos que en realidad ya serían otro flow.

---

## 1. Qué evidencia del repo apoya la idea

### 1.1. El runtime ya consume un bundle de prompts por carpeta

`run_negotiation_agent` no monta un motor distinto por caso; siempre construye un único config y ejecuta el mismo cognitive turn. La selección de prompts entra por `build_negotiation_pipeline_config()` y por `config.prompts_dir`. Eso hace que el pipeline ya sea, de hecho, **prompt-directory driven**. 

Además, en `run_negotiation_cognitive_turn` se cargan directamente desde `prompts_dir`:

- `summarizer_prompt.txt`
- `phase_classifier_prompt.txt`
- `planner_prompt.txt`
- `executor_prompt.txt`

Y tanto `build_phase_input` como `build_planner_input` / `build_executor_input` toman también assets del mismo directorio (`phase_classifier_card.json`, `phase_cards.json`).

**Implicación:** el motor actual ya separa parcialmente “lógica de ejecución” de “bundle de instrucciones/contexto”.

### 1.2. El estado canónico ya inyecta `persona` y `negotiation_brief` desde archivos

`build_default_canonical_state()` inicializa `persona` y `negotiation_brief` leyendo `persona.json` y `negotiation_brief.json`. Eso significa que dos casos distintos ya podrían, conceptualmente, arrancar con el mismo shape de estado pero con distinto contenido privado del caso.

**Implicación:** la noción de “context pack” no es extraña al diseño actual; ya existe de forma implícita.

### 1.3. Planner y executor ya dependen del contexto inyectado, no de lógica hardcodeada por caso

`PlannerInput` recibe:

- `persona_policy`
- `negotiation_brief`
- `current_phase`
- `phase_card`
- `negotiation_state`
- `planner_state`
- `scene_state`

`ExecutorInput` recibe:

- `persona_expressive`
- `current_phase`
- `phase_card`
- `planner_output`
- `scene_state`

Esto es importante porque el motor no cambia por caso: **cambia el payload que el motor le entrega al modelo**. Esa es exactamente la línea que tu hipótesis quiere explotar.

### 1.4. El optimizer ya demuestra que el sistema tolera variaciones de bundle

`experiments_bridge.apply_overrides()` ya puede:

- copiar el bundle base a un directorio temporal,
- sustituir prompts,
- sustituir `phase_cards.json`,
- sustituir `persona.json`,
- y volver a ejecutar el mismo motor con otro `prompts_dir`.

Aunque hoy no soporte todo lo que propones, esto es evidencia fuerte de viabilidad arquitectónica: el runtime no depende exclusivamente de archivos globales inmutables.

### 1.5. La evaluación ya está desacoplada del turno online

El pipeline de `evaluacion` construye un `FeedbackInputBundleV1` a partir de la sesión y luego ejecuta runners separados (`core` y `trajectory`). Sus prompts viven aparte y la rúbrica del dominio vive en `backend/evaluacion/domains/negotiation/rubrics/negotiation_rubric_v1.json`.

**Implicación:** la evaluación ya tiene una frontera clara donde podría introducirse resolución por contexto sin tocar el motor conversacional.

---

## 2. Qué partes sí encajan bien con el modelo `context pack`

## 2.1. Prompts del flujo

Encajan muy bien:

- `planner_prompt.txt`
- `executor_prompt.txt`
- `summarizer_prompt.txt`
- `phase_classifier_prompt.txt`

Son los candidatos más obvios para variar por caso, porque ya están fuera del código y el motor solo los lee.

### 2.2. Assets estáticos del caso

También encajan bien:

- `persona.json`
- `negotiation_brief.json`
- `phase_cards.json`
- `phase_classifier_card.json`

Especialmente `persona.json` y `negotiation_brief.json`, porque hoy ya forman parte del estado inicial y del input del planner.

### 2.3. Parte importante de la evaluación

También es razonable llevar por contexto:

- `core_evaluator_prompt.txt`
- `trajectory_evaluator_prompt.txt` si quieres matices por caso
- rúbrica de evaluación
- fixtures o bundles de prueba por caso

La tubería de evaluación no necesita saber cómo “negocia” el caso en runtime; solo necesita un bundle coherente con el contexto que está evaluando.

### 2.4. Resolución pública por URL

A nivel conceptual, la idea:

- `/actividad/negociacion/mustang`
- `/actividad/negociacion/salario`
- `/actividad/negociacion/proveedor`

encaja bien con la arquitectura actual, porque la UI pública ya es una superficie separada (`/interfaz_usuario`) y la sesión ya tiene bootstrap y turn API dedicados. No existe todavía esa resolución, pero **la arquitectura no la contradice**.

### 2.5. Fijación de contexto en sesión

También encaja bien si se hace explícito. La sesión ya tiene `world_state` y el canonical state ya persiste en `world_state[memory_key]`. Añadir metadatos de contexto a nivel sesión sería una extensión natural de esa persistencia, no un injerto raro.

---

## 3. Qué partes no encajan del todo con la simplificación

## 3.1. `NegotiationState` no es neutro respecto al dominio real

Aunque el shape es reusable para muchas negociaciones, no es completamente agnóstico. Tiene conceptos concretos como:

- ofertas de ambas partes,
- acuerdo tentativo,
- `stall_state`,
- `blockers`,
- `active_axes`,
- `next_open_loop`.

Eso sirve bien para variantes de negociación distributiva/integrativa con intercambio verbal, pero presupone que todos los casos caben ahí. Si un caso necesitara memoria estructurada distinta —por ejemplo múltiples actores, aprobaciones externas, entregables por etapas, dependencias legales, calendario rígido— el pack de prompts podría quedarse corto.

## 3.2. El phase system es fijo y cerrado

El enum `NegotiationPhase` está cerrado a seis fases:

- `clima_humano`
- `descubrimiento_y_comprension`
- `propuesta_creativa`
- `concesiones_y_ajuste_final`
- `formalizacion_del_acuerdo`
- `abandono_de_la_negociacion`

Esto es una restricción fuerte. Aunque cambies `phase_cards.json` y el prompt del clasificador, **no puedes cambiar desde contexto el conjunto de fases ni su identidad semántica**. Por tanto, el modelo de `context pack` es sólido solo si todos los casos siguen teniendo sentido dentro de ese phase model.

## 3.3. El memory node lleva semántica negociadora concreta

El prompt de `summarizer_prompt.txt` no solo resume: también reconstruye `negotiation_state` con reglas muy concretas sobre:

- ofertas activas,
- ejes activos (`price`, `extras`, `paperwork`, `closing_timing`, `transfer_costs`, `delivery`, `risk`, `warranty`),
- acuerdos tentativos,
- bloqueos,
- ultimátum y atasco.

Eso quiere decir que gran parte de la “variabilidad por caso” sí puede ir en prompt, pero el **schema subyacente del estado** ya está orientado a un tipo de negociación bastante específico. Si un nuevo caso no comparte esa gramática, el pack no bastará.

## 3.4. La UI actual no está aislada del significado del flujo

La UI no es puramente genérica. Tiene:

- finalización basada en `finish_button_armed`;
- evaluación posterior ligada al dominio negociación;
- bootstrap de sesiones y reinicio de conversación;
- metadatos visibles como `conversation_id`, `trace_count`, etc.

No está muy acoplada al caso Mustang como contenido, pero sí a la semántica de “hay una negociación con cierre/finalización y feedback asociado”. Por eso la UI puede mantenerse casi igual entre contextos del mismo flujo, pero no es un shell universal libre de semántica.

## 3.5. La evaluación actual no es todavía “case-aware”

La evaluación sí es de dominio, pero no selecciona caso/contexto. El extractor construye `DomainContext(domain="negociacion", final_phase=..., finish_button_was_armed=...)`, pero no mete `context_id`, ni `persona`, ni `brief`, ni rúbrica por caso.

Eso significa que una parte de la simplificación propuesta es viable, pero **todavía no existe la resolución canónica de contexto** en evaluación.

## 3.6. El optimizer hoy trabaja con overrides, no con contextos oficiales

El optimizer puede modificar prompts y parte del contexto, pero no opera sobre un `context_id` estable. Su modelo actual es más bien:

- sesión espejo o sandbox,
- overrides por prompt/config/contextual,
- directorio temporal efectivo.

Eso sirve para experimentar, pero no equivale todavía a “simular la URL pública del caso X”.

---

## 4. Respuestas a las preguntas clave

## 4.1. ¿Es cierto que lo que define un caso/contexto son sobre todo prompts y JSON fijos?

**Sí, pero solo en el perímetro de “mismo tipo de negociación”.**

Es sustancialmente cierto cuando cambian:

- la identidad/voz de la contraparte o del agente,
- el brief privado,
- el contenido de las fases,
- la lógica verbal de clasificación de fase,
- la rúbrica evaluativa,
- los ejemplos/fixtures del caso.

Deja de ser suficiente cuando cambia:

- el conjunto de fases;
- el tipo de estado necesario;
- la semántica de cierre;
- el mapa de ejes negociables;
- o la forma de extraer/evaluar desempeño.

## 4.2. ¿Qué partes sí podrían variar solo por `context pack`?

Sí podrían variar así, con alta probabilidad de éxito:

- prompts de memory/planner/executor/phase classifier;
- `persona.json`;
- `negotiation_brief.json`;
- `phase_cards.json`;
- `phase_classifier_card.json`;
- prompts y rúbricas de evaluación;
- datasets/fixtures/evals por caso;
- copy visible de la URL pública si la UI muestra nombre del caso.

## 4.3. ¿Qué partes NO encajan tan fácilmente?

No encajan tan fácil:

- `NegotiationPhase` como enum cerrado;
- ciertas expectativas del memory prompt sobre ejes activos;
- `finish_button_armed` si el caso no usa cierre/acuerdo/abandono igual;
- el extractor/evaluador si la noción de buen desempeño depende de hechos del contexto que hoy no viajan en el bundle de evaluación;
- el optimizer si se quiere trazabilidad oficial por caso sin ambigüedad.

## 4.4. ¿El phase system es reusable o está demasiado tuned?

Está **bastante reusable para casos afines**, pero no es universal.

La estructura de seis fases describe bien una negociación conversacional bilateral con:

- apertura humana,
- descubrimiento,
- propuesta,
- ajuste/concesiones,
- cierre,
- abandono.

Eso es suficientemente reusable entre muchos casos. Lo que no soporta bien es un caso cuya secuencia natural sea distinta o necesite fases adicionales/alternativas. En ese punto el problema ya no es de prompts, sino del modelo de fases.

## 4.5. ¿`NegotiationState` soporta bien la idea?

La soporta **razonablemente bien para variantes del mismo flow**, porque es un estado táctico genérico y no un estado “Mustang-only”.

Pero también oculta acoplamientos:

- presupone ofertas relativamente compactas;
- presupone negociación bilateral;
- presupone cierto set de axes;
- presupone que el progreso puede modelarse con `stall_state`, blockers y open loops;
- no contempla objetos de contexto versionados o metadatos de caso en sesión.

## 4.6. ¿La evaluación puede resolverse por contexto?

**Sí, pero no solo cambiando prompts**.

Cambiar prompts/rúbrica por contexto es la parte más directa. Pero para que la evaluación sea realmente robusta por contexto haría falta que el bundle de entrada de evaluación también supiera **qué contexto se evaluó**. Si no, corres el riesgo de evaluar una conversación de un caso con una rúbrica de otro.

## 4.7. ¿La UI puede mantenerse casi igual?

**Sí**, siempre que todos los contextos compartan el mismo contrato conversacional:

- misma mecánica de turnos,
- mismo finalizador,
- misma evaluación,
- misma noción de “una conversación = una negociación”.

La UI actual no parece exigir semántica de Mustang, pero sí exige semántica de negociación con cierre.

## 4.8. ¿El optimizer podría funcionar solo eligiendo `context_id`?

**Como idea objetivo, sí. En el estado actual, no del todo.**

Hoy necesitaría además:

- fijar el bundle de prompts/contexto efectivo;
- marcar la sesión sandbox con ese contexto;
- incluir el contexto en trazas y comparaciones;
- y distinguir claramente overrides experimentales versus contexto base oficial.

## 4.9. ¿Qué riesgos de contaminación entre contextos habría?

Los más claros son:

- reutilizar una sesión con canonical state creado para otro contexto;
- reusar `conversation_id` OpenAI entre contextos distintos;
- evaluar con rúbrica equivocada;
- mezclar trazas del optimizer de un contexto con otro;
- auto-reset o “new conversation” sin reset de contexto;
- clonado sandbox desde una sesión origen de un caso distinto.

## 4.10. ¿Qué tendría que fijarse en sesión?

Mínimo:

- `context_id` canónico;
- versión del contexto o `context_pack_version`;
- ruta o identificador del bundle resuelto;
- identidad del dominio/flow (`negociacion`);
- quizá `evaluation_context_id` si puede divergir por versión;
- y preferiblemente la huella/hash del bundle efectivo para trazabilidad.

Además, al crear una nueva conversación dentro de la misma actividad, debe heredarse explícitamente el mismo contexto, no volver al default de forma implícita.

## 4.11. ¿Simplifica de verdad o solo parece simple?

**Simplifica de verdad**, pero solo si se declara su frontera:

- sirve para múltiples casos dentro del mismo flow de negociación;
- no sustituye un cambio de flow cuando cambian fases, estado o semántica;
- no elimina la necesidad de fijación de contexto en sesión/trazas/evaluación.

La simplicidad es real en el runtime, pero puede ser engañosa si se vende como solución universal para cualquier “negociación”.

## 4.12. ¿Dónde podría romperse con casos futuros?

Se rompería sobre todo si aparece un caso con:

- múltiples contrapartes;
- negociación no bilateral;
- aprobaciones externas como parte central del flujo;
- semántica de cierre no reducible a acuerdo/abandono;
- ejes estructurados no representables en `active_axes` actuales;
- necesidad de extraer hechos no cubiertos por `NegotiationOffer` o `TentativeAgreement`;
- evaluación que depende de reglas de dominio no expresables con una rúbrica del tipo actual.

## 4.13. ¿Qué parte de la arquitectura previa sigue siendo útil?

Sigue siendo muy útil casi todo lo que ya existe:

- pipeline multi-nodo;
- canonical state;
- traces ricos;
- guardrails;
- entry contract;
- surface parity-safe de `interfaz_usuario`;
- optimizer sandbox;
- pipeline de evaluación asíncrono.

La simplificación no invalida esa arquitectura; más bien la ordena alrededor de un concepto explícito de contexto.

---

## 5. Diagnóstico final de viabilidad

## Veredicto

**Viable con matices.**

La mejor formulación, aterrizada al repo real, sería esta:

> Dentro del flow actual `negociacion`, varios casos distintos sí pueden modelarse mayoritariamente como bundles de prompts + assets JSON + evaluación por contexto, siempre que compartan el mismo modelo de fases, el mismo shape de estado y la misma semántica base del flujo.

Eso significa que la propuesta es arquitectónicamente sana **si se restringe a “múltiples contextos dentro del mismo flow”** y no se usa para encubrir flows materialmente distintos.

## Recomendación

Sí merece la pena seguir por esta dirección, pero con tres precauciones:

1. **nombrar explícitamente los límites del flow** para que no todo caso se fuerce dentro de él;
2. **hacer el contexto una entidad de sesión/traza/evaluación**, no solo una ruta de archivos;
3. **separar nítidamente motor estable vs bundle contextual**, sin intentar volver configurable lo que hoy es estructural (enum de fases, schema de estado, contratos de salida).
