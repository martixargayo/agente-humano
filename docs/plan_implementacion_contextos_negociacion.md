# Plan de implementación realista: llevar `negociacion` a motor estable + contextos

## Propósito

Este documento convierte el análisis previo en un **plan de implementación por fases**, orientado a un objetivo muy concreto:

- mantener `backend/negociacion/` como motor estable;
- introducir resolución oficial de contextos dentro del mismo flow;
- permitir múltiples casos del flow por carpeta/URL;
- y hacerlo **sin cambiar el comportamiento funcional actual**.

La premisa de este plan es deliberadamente conservadora:

> el sistema debe seguir negociando igual que hoy; solo debe quedar mejor organizado para soportar varios contextos oficiales dentro del mismo flow.

---

## 1. Restricciones de implementación

## 1.1. Invariante principal

Mientras se ejecuta este plan, el comportamiento observable del caso actual debe permanecer igual en:

- contenido táctico del flow,
- orden del pipeline,
- shape del canonical state,
- guardrails,
- criterios de finalización,
- contratos de API existentes,
- evaluación ya expuesta en UI,
- optimizer actual en modo base.

## 1.2. Qué NO intenta resolver este plan

Este plan no intenta:

- rediseñar `NegotiationPhase`;
- cambiar `NegotiationState`;
- introducir un framework genérico de activities/flows/plugins;
- rediseñar la UI pública;
- cambiar la forma de negociar del sistema;
- rehacer la evaluación desde cero;
- hacer una migración masiva de estructura en un solo paso.

## 1.3. Definición operativa de éxito

El plan se considera bien ejecutado si, al finalizar, ocurre esto:

1. el contexto actual por defecto produce el mismo comportamiento funcional que hoy;
2. el runtime puede resolver un `context_id` oficial;
3. la sesión queda fijada a ese `context_id`;
4. prompts/assets/evaluación se leen desde el contexto correcto;
5. el optimizer puede simular un contexto oficial y dejarlo visible en trazas;
6. el caso actual sigue funcionando aunque solo exista un contexto inicial equivalente al bundle de hoy.

---

## 2. Lectura del repo actual que condiciona el plan

El plan parte de estos hechos del repo real:

- el runtime de negociación ya depende de un `prompts_dir` único dentro de `NegotiationTurnConfig`;
- el motor ya lee prompts y assets del filesystem;
- el canonical state ya carga `persona.json` y `negotiation_brief.json` desde disco al construir defaults;
- la UI pública usa `bootstrap`, `new_conversation` y `turn` sobre una sesión sin `context_id` explícito;
- la evaluación se construye a partir de sesión e historial, pero no persiste contexto;
- el optimizer ya soporta bundle temporal por overrides, pero no un contexto oficial estable.

Eso permite una implementación incremental y de bajo riesgo: no hay que inventar un nuevo motor; hay que **introducir resolución explícita de contexto y propagarla de forma segura**.

---

## 3. Estrategia general de migración

La estrategia recomendada es de **doble compatibilidad temporal**, no de corte brusco.

### Principio

Primero se introduce la capacidad de resolver contexto oficial **sin mover todavía el comportamiento base**.

### Secuencia lógica

1. introducir un concepto mínimo de `context_id` oficial;
2. introducir un contexto por defecto equivalente a lo que hoy vive en `backend/negociacion/prompts/` y `backend/evaluacion/...`;
3. hacer que el runtime pueda resolver ese contexto sin cambiar resultados;
4. fijar el contexto en sesión;
5. extender esa resolución a evaluación y optimizer;
6. solo después preparar contextos adicionales.

Este orden minimiza riesgo porque siempre existe un “contexto default = comportamiento actual”.

---

## 4. Fases de implementación

## Fase 0 — Congelar baseline funcional y definir invariantes

### Objetivo

Tener un baseline verificable antes de tocar resolución de contexto.

### Trabajo propuesto

- Identificar el caso actual como **baseline oficial** del flow.
- Declarar por escrito qué bundle actual representa ese baseline:
  - prompts de `backend/negociacion/prompts/`
  - assets JSON de `backend/negociacion/prompts/`
  - prompts/rúbrica de `backend/evaluacion/`
- Documentar los invariantes que no pueden cambiar.
- Seleccionar trazas/sesiones/casos de referencia en optimizer/evals para comparación futura.

### Entregables

- un documento corto de “baseline actual del flow”;
- una checklist de invariantes funcionales;
- una lista de smoke tests manuales y de regresión observable.

### Riesgo

Bajo.

### Por qué va primero

Porque evita que la migración se convierta en una refactorización “correcta” pero imposible de validar contra el comportamiento original.

---

## Fase 1 — Introducir un modelo mínimo de contexto oficial

### Objetivo

Definir una unidad oficial de contexto **sin alterar todavía cómo ejecuta el runtime**.

### Trabajo propuesto

Introducir solo a nivel de estructura y resolución estos conceptos:

- `flow_id = negociacion`
- `context_id`
- `context_version`
- ubicación física del contexto

### Decisión recomendada

Usar una raíz conceptual como:

```text
backend/negociacion/contexts/<context_id>/
```

con un único contexto inicial equivalente al caso actual.

### Alcance de esta fase

- definir estructura de carpetas;
- definir un `manifest.json` mínimo;
- copiar o reflejar el bundle actual en un contexto baseline;
- documentar correspondencia 1:1 entre bundle actual y contexto baseline.

### Qué no hacer aún

- no cambiar routers públicos;
- no cambiar session handling;
- no cambiar evaluación;
- no cambiar optimizer;
- no borrar todavía el bundle original si eso aumenta riesgo.

### Criterio de salida

Existe una representación oficial del contexto actual como carpeta de contexto, aunque el runtime principal aún no dependa de ella en producción.

---

## Fase 2 — Resolver contexto en runtime sin cambiar comportamiento

### Objetivo

Hacer que el runtime de `negociacion` pueda construir `NegotiationTurnConfig` y defaults del estado a partir de un contexto oficial, manteniendo el mismo bundle efectivo que hoy.

### Trabajo propuesto

Introducir una capa mínima de resolución para responder preguntas como:

- cuál es el `context_id` activo;
- cuál es su `prompts_dir`;
- dónde están sus assets de evaluación;
- cuál es su versión/hash.

### Aplicación concreta en el repo

Esta resolución impacta principalmente en:

- construcción de `NegotiationTurnConfig`;
- carga de prompts del flow;
- carga de `phase_cards.json` y `phase_classifier_card.json`;
- carga de `persona.json` y `negotiation_brief.json` al crear el canonical state.

### Regla clave de esta fase

El contexto por defecto debe apuntar al bundle actual o a un clon exacto del mismo. El comportamiento resultante debe ser indistinguible.

### Qué sí cambia

- la fuente de resolución del bundle;
- no la semántica del bundle.

### Qué no cambia

- contratos de nodos;
- orden de ejecución;
- prompts efectivos del caso actual;
- models/limits;
- traces existentes salvo metadatos añadidos.

### Riesgos a vigilar

- introducir defaults implícitos inconsistentes entre runtime y canonical state;
- que `build_default_canonical_state()` siga leyendo de una ruta distinta a la del runtime efectivo;
- discrepancias entre `prompts_dir` y los JSONs por defecto del estado.

### Criterio de salida

El runtime puede ejecutarse con `context_id=default_actual` y producir el mismo comportamiento del caso actual.

---

## Fase 3 — Fijar el contexto en sesión y proteger contra contaminación

### Objetivo

Asegurar que cada sesión queda ligada a un único contexto oficial.

### Trabajo propuesto

Añadir metadatos de contexto en sesión/canonical state o en una zona claramente accesible desde ambos. Mínimo recomendado:

- `flow_id`
- `context_id`
- `context_version`
- `context_pack_hash` opcional

### Aplicación concreta

Afecta sobre todo a:

- `bootstrap_session`
- creación de `new_conversation`
- `run_turn`
- creación de sandbox/new conversation en optimizer

### Reglas operativas

1. una sesión nueva debe nacer con contexto resuelto explícitamente;
2. una nueva conversación derivada debe heredar el mismo contexto salvo que se pida otro explícitamente;
3. un turno no debe aceptar mezclar bundle de contexto y sesión preexistente incompatibles;
4. cambiar de URL no debe “mutar” silenciosamente una sesión ya iniciada con otro contexto.

### Compatibilidad

Para no romper el comportamiento actual, el `bootstrap` existente puede seguir aceptando payload antiguo y resolver el contexto baseline por defecto.

### Criterio de salida

Toda sesión de `negociacion` tiene identidad contextual explícita y estable.

---

## Fase 4 — Resolver contexto desde la URL pública con compatibilidad hacia atrás

### Objetivo

Hacer que la superficie pública pueda elegir contexto por URL sin romper el endpoint actual ni la UI existente.

### Estrategia recomendada

Introducir primero la resolución de contexto en la capa de entrada, manteniendo el endpoint y payload actual como compatibles.

### Aplicación concreta

Posibles pasos conservadores:

1. mantener `/interfaz_usuario` y `/api/interfaz_usuario/...` intactos para el baseline actual;
2. añadir una forma explícita de bootstrapear contexto desde una URL o slug público;
3. mapear esa resolución a `context_id` antes de crear sesión;
4. dejar el flujo actual funcionando aunque no se use todavía una nueva URL pública final.

### Qué evitar en esta fase

- reescribir la app front completa;
- introducir lógica ambigua donde el frontend y el backend resuelvan contextos distintos;
- forzar cambio de contrato si todavía no hay más de un contexto desplegado.

### Recomendación

El backend debe ser la fuente de verdad de la resolución `URL -> context_id`. El frontend puede enviar slug, pero la validación y resolución final deben quedar en backend.

### Criterio de salida

Existe una ruta compatible para resolver contexto desde entrada pública, sin romper el acceso actual al baseline.

---

## Fase 5 — Propagar contexto a trazas, diagnóstico y entry contracts

### Objetivo

Volver visible el contexto efectivo en observabilidad y debugging.

### Trabajo propuesto

Añadir a trazas y metadatos del turno:

- `flow_id`
- `context_id`
- `context_version`
- `context_pack_hash` si existe
- indicador de bundle oficial vs bundle con overrides

### Por qué esta fase es importante

Sin esto, el sistema podría funcionar técnicamente con contextos, pero seguiría siendo difícil demostrar:

- qué contexto produjo una conversación,
- si una traza pertenece al baseline o a un experimento,
- o si evaluación/optimizer están alineados con la URL pública.

### Compatibilidad

Esta fase no altera la negociación; solo enriquece observabilidad.

### Criterio de salida

Un turno permite saber inequívocamente con qué contexto oficial se ejecutó.

---

## Fase 6 — Hacer la evaluación context-aware sin cambiar el pipeline base

### Objetivo

Mantener el mismo pipeline de evaluación, pero haciendo que sus prompts/rúbrica se resuelvan por contexto.

### Trabajo propuesto

Separar claramente:

- la parte estable del pipeline de evaluación,
- de los assets evaluativos que pasan a depender del contexto.

### Aplicación concreta

Esta fase afecta a:

- construcción del `FeedbackInputBundleV1`;
- `DomainContext` o metadatos equivalentes;
- resolución de prompts de `core` y `trajectory`;
- resolución de rúbrica del dominio/caso;
- persistencia de contexto en job/report/provenance.

### Regla clave

No cambiar el pipeline `bundle -> runners -> reconciliation -> report`; solo cambiar la resolución del bundle evaluativo y la identidad contextual que viaja con él.

### Compatibilidad

El contexto baseline debe seguir usando exactamente la misma rúbrica/prompts que hoy.

### Criterio de salida

Una evaluación sabe qué contexto evaluó y usa sus assets correctos, manteniendo la misma forma general de reporte.

---

## Fase 7 — Hacer el optimizer context-aware manteniendo overrides

### Objetivo

Permitir que el optimizer seleccione un contexto oficial y experimente encima de él.

### Trabajo propuesto

Evolucionar el optimizer desde:

- “override store + temp bundle”

a:

- “contexto oficial base + overrides opcionales”.

### Aplicación concreta

El optimizer debería poder:

1. elegir `context_id` oficial;
2. clonar/sandboxear una sesión manteniendo ese contexto;
3. ejecutar el mismo runtime que la URL pública del contexto;
4. añadir overrides por encima;
5. reflejar todo eso en trazas y comparaciones.

### Qué conservar

- el modo sandbox actual;
- la capacidad de prompt overrides;
- la comparación de turns;
- la resolución por conversación/turno.

### Qué cambia

- aparece una noción de baseline contextual oficial, no solo bundle temporal implícito.

### Criterio de salida

El optimizer puede responder honestamente: “estoy probando el contexto oficial X, con/sin overrides”.

---

## Fase 8 — Crear el segundo contexto oficial

### Objetivo

Validar que la arquitectura ya soporta más de un contexto real sin tocar el motor.

### Regla de prudencia

Esto debe hacerse solo después de cerrar las fases anteriores. Antes, crear más contextos añade ruido y no valida bien la migración.

### Trabajo propuesto

- crear un segundo contexto de prueba del mismo flow;
- copiar el esquema del baseline;
- variar solo prompts/assets/evaluación según el caso;
- comprobar que URL, sesión, runtime, evaluation y optimizer resuelven ese contexto de punta a punta.

### Qué medir

- aislamiento entre sesiones/contextos;
- ausencia de mezcla en trazas;
- coherencia de evaluación;
- consistencia del optimizer con la URL pública.

### Criterio de salida

Dos contextos oficiales conviven dentro del mismo flow sin requerir cambios estructurales del motor.

---

## 5. Orden técnico recomendado de cambios

Para minimizar riesgo, el orden técnico concreto debería ser este:

1. documentación de baseline e invariantes;
2. estructura física de contextos + contexto baseline;
3. resolución interna de contexto para runtime;
4. alineación de `build_default_canonical_state()` con el contexto resuelto;
5. persistencia de `context_id` en sesión;
6. resolución de contexto en bootstrap/new conversation;
7. metadatos de contexto en trazas;
8. evaluación context-aware;
9. optimizer context-aware;
10. segundo contexto oficial.

Este orden reduce la probabilidad de romper comportamiento del caso actual.

---

## 6. Mapa de impacto por zona del repo

## `backend/negociacion/`

### Impacto esperado

Moderado y controlado.

### Qué tocaría primero

- resolución de contexto;
- construcción de `NegotiationTurnConfig`;
- lectura de bundle contextual;
- alineación entre runtime y defaults del canonical state.

### Qué no debería tocarse salvo necesidad real

- enums de fases;
- contratos de nodos;
- shape de `CanonicalState` y `NegotiationState`.

## `backend/interfaz_usuario/`

### Impacto esperado

Moderado.

### Enfoque

- ampliar bootstrap/new conversation para contexto;
- mantener compatibilidad con payload actual;
- asegurar herencia del contexto entre conversaciones.

## `backend/interfaz_usuario_app/`

### Impacto esperado

Bajo al principio.

### Enfoque

- resolver contexto desde la entrada pública de forma conservadora;
- no rediseñar la UI;
- mantener el flujo actual con el contexto baseline.

## `backend/evaluacion/`

### Impacto esperado

Moderado.

### Enfoque

- mantener pipeline;
- introducir resolución de assets evaluativos por contexto;
- persistir identidad contextual en bundle/job/report.

## `backend/negociacion/optimizador/`

### Impacto esperado

Moderado-alto.

### Enfoque

- conservar overrides actuales;
- superponerles contexto oficial;
- evitar que el optimizer invente otra vía paralela de resolución.

## `backend/sessions/`

### Impacto esperado

Crítico pero pequeño en superficie.

### Enfoque

- introducir identidad contextual explícita;
- proteger herencia/aislamiento;
- no rehacer el modelo de sesiones en RAM.

---

## 7. Riesgos concretos por fase

## Riesgo A — runtime y estado leen contextos distintos

Si `NegotiationTurnConfig.prompts_dir` apunta a un contexto y `build_default_canonical_state()` sigue leyendo JSONs globales, aparecerán inconsistencias sutiles.

### Mitigación

Resolver prompts y defaults del estado desde la misma identidad de contexto.

## Riesgo B — sesiones legacy sin `context_id`

Las sesiones antiguas o creadas por endpoints legacy pueden quedar sin identidad contextual.

### Mitigación

Backfill conservador al contexto baseline por defecto.

## Riesgo C — optimizer queda más avanzado que la URL pública

El optimizer podría soportar contexto oficial antes que la UI pública y crear una brecha conceptual.

### Mitigación

Definir que el backend resuelve contexto de forma única y que optimizer reutiliza esa resolución.

## Riesgo D — evaluación usa assets del contexto incorrecto

### Mitigación

Persistir `context_id` en bundle/job/provenance antes de habilitar varios contextos reales.

## Riesgo E — la migración se convierta en refactor estructural

### Mitigación

Mantener como regla que cada fase debe preservar comportamiento baseline antes de pasar a la siguiente.

---

## 8. Criterios de aceptación por fase

## Fase 1 aceptada si

- existe estructura oficial de contextos;
- existe un contexto baseline equivalente al actual;
- no hay cambio funcional aún.

## Fase 2 aceptada si

- runtime resuelve contexto baseline;
- prompts/assets efectivos son los mismos que hoy;
- no cambian outputs esperados del caso actual.

## Fase 3 aceptada si

- cada sesión de negociación tiene `context_id` estable;
- `new_conversation` hereda contexto;
- no hay mezcla accidental entre contextos.

## Fase 4 aceptada si

- la entrada pública puede resolver contexto;
- el acceso actual sigue funcionando para baseline.

## Fase 5 aceptada si

- cada traza identifica contexto oficial;
- comparar turns por contexto ya es posible.

## Fase 6 aceptada si

- la evaluación resuelve prompts/rúbrica por contexto;
- el pipeline y formato del reporte siguen igual.

## Fase 7 aceptada si

- el optimizer elige contexto oficial;
- las trazas reflejan contexto + overrides.

## Fase 8 aceptada si

- existe un segundo contexto real funcionando sin cambios del motor.

---

## 9. Recomendación de alcance para la primera implementación real

Si hubiera que convertir este plan en la **primera implementación efectiva**, el corte más prudente sería:

### Primera entrega de implementación

- Fase 1 completa
- Fase 2 completa
- Fase 3 mínima
- Fase 5 mínima

### Qué dejar fuera de esa primera entrega

- resolución pública final por URL si aún complica demasiado frontend;
- evaluación completa context-aware;
- optimizer completo context-aware;
- segundo contexto oficial.

### Por qué

Porque ese corte ya produce la pieza más importante:

> el runtime queda preparado para contextos oficiales sin cambiar el comportamiento del caso actual.

Y deja el resto como propagación controlada, no como big bang.

---

## 10. Recomendación final

La forma más segura de llevar este repo al modelo `motor estable + contextos` es una migración en dos tiempos:

### Tiempo 1

Hacer **oficial** el contexto actual sin cambiar comportamiento.

### Tiempo 2

Propagar esa identidad oficial a sesión, URL, evaluación y optimizer.

Esa secuencia está alineada con el repositorio real y con tu restricción más importante:

> no cambiar cómo negocia el sistema; solo reorganizarlo para que pueda soportar varios contextos del mismo flow.

La conclusión práctica del plan es esta:

- sí conviene seguir por esta estrategia;
- sí conviene hacerlo por fases;
- y la primera implementación debe centrarse en **introducir identidad contextual y resolución unificada**, no en crear todavía muchos contextos nuevos.
