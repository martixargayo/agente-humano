# Riesgos y límites del modelo `context pack` en `negociacion`

## Tesis central

El modelo “mismo motor + mismo pipeline + distinto pack de prompts/JSON/evaluación” es atractivo porque encaja con bastante de la arquitectura actual. Pero **puede ser engañoso** si se interpreta como “todo nuevo caso de negociación cabe aquí sin tocar nada estructural”.

Este documento separa:

- riesgos reales inmediatos,
- riesgos a medio plazo,
- y límites naturales del modelo.

---

## 1. Riesgos reales inmediatos

## 1.1. Contaminación de sesión entre contextos

Hoy la sesión se identifica por `(user_id, session_id)` y persiste `world_state`, `history`, `summary` y trazas en memoria. Si el contexto no queda fijado explícitamente en sesión, un mismo `session_id` podría:

- arrancar con `persona/brief` de un caso;
- seguir después con prompts de otro caso;
- conservar `negotiation_state` y `planner_state` del caso anterior;
- y producir una conversación híbrida difícil de diagnosticar.

### Impacto

Muy alto. Es el riesgo más importante si se adopta URL → contexto.

### Señales de fragilidad en el repo

- la sesión no guarda hoy `context_id`;
- `build_default_canonical_state()` carga defaults globales desde `backend/negociacion/prompts/`;
- `new_conversation` crea sesión nueva, pero no arrastra ni fija contexto oficial.

## 1.2. Contaminación de threading OpenAI entre contextos

`CanonicalState.openai_thread` persiste `conversation_id` y `previous_response_id`. Si se cambia el contexto sin reinicializar o separar correctamente la conversación, podría arrastrarse continuidad conversacional del proveedor LLM entre casos distintos.

### Impacto

Alto. El sistema podría mezclar memoria implícita del hilo con un pack nuevo.

### Qué lo agrava

- `planner` y `executor` son nodos “stateful_sequential” y sí reutilizan contexto de conversación;
- el entry surface actual no asocia conversación OpenAI a un contexto explícito.

## 1.3. Falsa sensación de aislamiento porque los prompts cambian pero el estado no

Cambiar prompt files puede parecer suficiente, pero el canonical state ya contiene:

- `persona`
- `negotiation_brief`
- `negotiation_state`
- `planner_state`
- `scene_state`
- `ui_state`

Si al seleccionar otro contexto solo cambian archivos y no se garantiza un canonical state compatible, el nuevo caso heredará historia táctica anterior.

### Impacto

Alto. Puede producir errores silenciosos, no crashes evidentes.

## 1.4. Evaluación con contexto equivocado

La evaluación actual no incluye `context_id` en el bundle de entrada. Si se adoptan varias rúbricas/prompts por contexto sin fijar el contexto en la evaluación, existe riesgo de:

- aplicar rúbrica Mustang a una conversación salario;
- producir informes válidos formalmente pero incorrectos semánticamente;
- dificultar comparabilidad histórica.

### Impacto

Alto en confianza del sistema.

## 1.5. Optimizer sin identidad oficial del contexto

El optimizer ya soporta overrides, pero no una noción oficial de “estoy probando el contexto `proveedor` versión X”. Eso puede generar:

- trazas difíciles de comparar;
- experimentos mezclados con contexto base no explícito;
- imposibilidad de saber si una mejora viene del prompt experimental o del cambio de contexto.

### Impacto

Medio-alto.

---

## 2. Riesgos a medio plazo

## 2.1. El phase system puede quedar demasiado estrecho

El enum fijo de fases funciona mientras todos los casos sigan la misma dramaturgia negociadora. A medio plazo, puede aparecer presión para meter casos que requieran:

- precalificación previa,
- evaluación de requisitos,
- aprobación interna,
- renegociación postacuerdo,
- negociación multipartita,
- o combinaciones menos lineales.

Si se intenta absorber todo eso solo mediante prompts, se puede degradar la calidad del sistema sin que el diseño lo admita explícitamente.

## 2.2. Crecimiento de reglas semánticas invisibles en prompts

Si cada contexto corrige limitaciones del motor añadiendo reglas cada vez más complejas al prompt, puede emerger una arquitectura donde:

- la lógica real del sistema vive dispersa en `.txt`;
- el comportamiento depende demasiado de disciplina editorial;
- y resulta difícil saber qué pertenece al motor y qué al caso.

Eso no invalida el modelo, pero sí exige gobernanza clara del bundle contextual.

## 2.3. Deriva del estado estructural

El estado actual ya está bien orientado a negociación bilateral. A medio plazo, distintos contextos pueden empujar a meter nuevos campos ad hoc en `NegotiationState` hasta convertir el supuesto “motor estable” en un motor progresivamente sesgado por acumulación de excepciones.

## 2.4. Divergencia entre UI pública y optimizer

Si la UI resuelve contexto por URL y el optimizer sigue trabajando por overrides informales, se abrirá una brecha entre:

- lo que “ve el usuario real”,
- y lo que “prueba el diseñador”.

Ese desfase es especialmente peligroso si se quiere usar el optimizer como espejo fiable del comportamiento público.

## 2.5. Reutilización excesiva de una rúbrica demasiado general

La rúbrica actual de negociación es suficientemente amplia, pero si se multiplican casos distintos puede quedarse demasiado abstracta. El riesgo no es solo técnico: también es de calidad de evaluación. Podría terminar dando informes muy parecidos para casos que exigen competencias distintas.

---

## 3. Límites naturales del modelo

## 3.1. Cuando cambian las fases, ya no basta un `context pack`

Si el caso necesita cambiar el conjunto mismo de fases, sus transiciones o su semántica profunda, ya no estamos ante “mismo flow, distinto contexto”.

Ese es el límite más claro.

## 3.2. Cuando cambia el tipo de memoria estructurada

Si el caso necesita recordar entidades o relaciones que no caben en:

- ofertas,
- acuerdo tentativo,
- blockers,
- stall state,
- open loop,
- axes activos,

entonces el pack de prompts ya no basta. El estado estructural tendría que cambiar.

## 3.3. Cuando la UI deja de significar lo mismo

Si un caso no comparte la semántica de:

- “tener turnos de negociación”
- “poder finalizar”
- “tener feedback del desempeño”

entonces mantener la misma UI deja de ser una simplificación real. Sería una reutilización artificial.

## 3.4. Cuando la evaluación depende de verdad del caso

Cambiar prompt y rúbrica sirve bastante, pero si la evaluación necesita:

- features derivadas nuevas,
- facts estructurados del contexto,
- validaciones específicas,
- o nuevas dimensiones de output,

ya no basta con “otro prompt”. El pipeline de input shaping/extracción también entra en juego.

## 3.5. Cuando hay varios actores o varios hilos sustantivos

El runtime actual está claramente centrado en una negociación bilateral con continuidad lineal. Si aparecen:

- varias contrapartes,
- aprobadores externos,
- conversaciones paralelas,
- o negociación por subtareas,

la simplificación deja de aguantar bien.

---

## 4. Acoplamientos reales que no conviene ignorar

## 4.1. Acoplamiento entre phase system y finish button

El botón de finalizar se arma cuando la fase actual es:

- `formalizacion_del_acuerdo`, o
- `abandono_de_la_negociacion`.

Eso une UI y semántica de fases. Si un contexto usa otro patrón de cierre, no bastará con cambiar prompts.

## 4.2. Acoplamiento entre memory prompt y `active_axes`

El prompt del nodo memory define un conjunto cerrado de ejes negociadores. Esa lista no vive en un asset contextual sino en la lógica textual del prompt base.

Si distintos contextos usan otros ejes como núcleo, hay dos opciones malas:

- forzarlos dentro del set actual, perdiendo precisión;
- o hacer crecer prompts cada vez más particulares.

## 4.3. Acoplamiento entre extractor de evaluación y estado canónico

El extractor actual deriva `final_phase` y `finish_button_was_armed`, pero no extrae facts de contexto. Eso acopla la evaluación más a la estructura general del flow que al caso concreto.

## 4.4. Acoplamiento entre optimizer y bundle incompleto

El optimizer solo soporta overrides oficiales para:

- prompts,
- `phase_cards`,
- `persona`,
- y algunos config fields.

No soporta hoy de forma nativa:

- `negotiation_brief`,
- `phase_classifier_card`,
- rúbrica de evaluación por contexto,
- ni `context_id` persistente.

Eso no invalida la idea, pero sí muestra que el soporte actual es parcial.

---

## 5. Simplificaciones engañosas que conviene evitar

## 5.1. “Si los prompts cambian, el contexto ya cambió”

No. Si no cambia también la identidad persistida de la sesión, el sistema puede seguir operando con restos del contexto anterior.

## 5.2. “La URL selecciona contexto, luego ya está resuelto”

No. La URL puede resolver el contexto inicial, pero luego ese contexto tiene que quedar fijado en sesión, trazas, evaluación y optimizer.

## 5.3. “La rúbrica por contexto arregla la evaluación”

No del todo. También necesitas asegurar que el bundle evaluado corresponde a ese contexto y que el pipeline sabe cuál es.

## 5.4. “Mientras no toque Python, sigo en el mismo flow”

Tampoco. Puede haber casos que conceptualmente ya sean otro flow aunque técnicamente intenten meterse a base de prompts.

---

## 6. Señales de que un nuevo caso ya no debería entrar en este modelo

Un nuevo caso debería considerarse fuera del modelo simple cuando ocurra cualquiera de estas señales:

1. necesita fases distintas a las seis actuales;
2. necesita estado estructural nuevo imprescindible para razonar bien;
3. la calidad del caso depende de datos que no caben en `persona/brief/phase_cards`;
4. la evaluación requiere extractor o schemas nuevos;
5. el cierre no se parece a acuerdo/abandono/finalización;
6. la UI necesitaría cambiar su contrato principal y no solo copy/contexto;
7. el optimizer necesita simular más que “otro bundle” y empieza a alterar semántica base del flow.

---

## 7. Conclusión dura y honesta

La estrategia `context pack` **sí simplifica** el problema correcto: soportar **múltiples casos homogéneos** dentro del flow actual de `negociacion`.

Pero tiene límites claros:

- no sustituye un diseño de flow distinto;
- no vuelve neutro un phase system que hoy es fijo;
- no vuelve universal un estado que ya presupone cierta forma de negociar;
- y no evita la necesidad de identidad contextual en sesión, trazas, evaluación y optimizer.

La forma sana de adoptarla es asumir explícitamente esta regla:

> “Cambiar prompts + JSONs + evaluación basta solo mientras el caso siga cabiendo honestamente dentro del mismo contrato conversacional, mismo modelo de fases y mismo shape de estado.”
