# Evaluación de impacto sobre el flujo de negociación con Redis sessions

## Resumen

La migración propuesta **no debería cambiar la lógica negociadora** si se implementa correctamente. El planner, el phase classifier, el executor y los prompts pueden mantenerse prácticamente intactos. El riesgo no está en el razonamiento del flujo, sino en **la fidelidad del snapshot de sesión** que se rehidrata en cada turno.

Dicho sin suavizarlo: si serializas mal el estado, puedes degradar la negociación aunque OpenAI siga devolviendo respuestas válidas. La degradación sería silenciosa y costaría mucho de detectar.

## ¿El flujo seguiría funcionando igual?

### Sí, si se preserva íntegro este bloque operativo
- `negotiation_canonical`
- `openai_thread`
- `memory_working`
- `negotiation_state`
- `planner_state`
- `recent_dialogue`
- binding de contexto
- binding de superficie

### No, si falta cualquiera de estas piezas clave
Porque el pipeline actual no es “stateless con prompt largo”; es un pipeline que usa snapshot operativo propio para decidir la táctica del siguiente turno.

## Qué partes del flujo podrían cambiar sin querer

### 1. `planner_state`
Si se pierde o se resetea al rehidratar:
- cambia la lectura de fase,
- se borra `current_turn_goal`,
- se desordena la continuidad táctica,
- puede reaparecer un tono de reinicio artificial.

### 2. `recent_dialogue`
Si se guarda truncado de forma distinta a hoy:
- el phase classifier verá otro contexto reciente,
- planner y executor cambiarán de foco,
- pueden aparecer repeticiones o preguntas que ya estaban resueltas.

### 3. `memory_working`
Si no se preserva:
- se pierde el tópico actual,
- se pierde la pregunta pendiente,
- se rompe la continuidad micro-táctica.

### 4. `negotiation_state`
Si se degrada:
- se pueden olvidar ofertas activas,
- se pueden perder bloqueos,
- se puede confundir el estado de cierre,
- aumentan los residuos tipo “volver a negociar algo ya asentado”.

### 5. `selected_memory`
Aunque parte de esta selección es derivada, si el snapshot base llega mal el planner puede seleccionar memoria equivocada y reforzar residuos o repeticiones.

## ¿Puede esta migración introducir residuos nuevos?

Sí, si se hace mal. En particular:

1. **Residuos por serialización parcial.**
   Guardas solo una parte del canónico y la otra se regenera por defaults.

2. **Residuos por compatibilidad laxa.**
   Una versión nueva rehidrata snapshots viejos sin migración ni validación estricta.

3. **Residuos por carreras.**
   Dos turnos leen la misma versión del snapshot y ambos guardan una versión distinta después.

4. **Residuos por lock expirado.**
   Un turno largo deja entrar otro a mitad y ambos pisan el `conversation_id` o el canónico.

## ¿Puede crear contaminación en cascada si se serializa mal?

Sí, y este es el riesgo principal.

Ejemplo típico:
1. se pierde `recent_dialogue` al guardar;
2. el planner compensa con una táctica menos precisa;
3. el memory node resume desde un contexto empobrecido;
4. el siguiente turno ya parte de un `memory_working` degradado;
5. la degradación se acumula sin que parezca un bug evidente.

Eso no es una mezcla entre usuarios, pero sí una forma real de “residuo operativo” dentro de la misma sesión.

## Riesgos si el estado en Redis no coincide con lo esperado por el pipeline

1. phase drift: el sistema cree estar en otra fase;
2. tactic drift: cambia el `turn_goal` implícito;
3. context drift: el planner olvida ofertas o preguntas pendientes;
4. tone drift: el executor responde como si fuera una conversación nueva;
5. trace drift: las trazas dejan de representar el estado real de decisión.

## Riesgos al rehidratar en cada turno

### Riesgos duros
- JSON corrupto,
- schema drift,
- snapshots incompletos,
- defaults silenciosos,
- desincronización entre `openai_thread` y estado local.

### Mitigaciones obligatorias
- validación estricta con Pydantic del snapshot cargado,
- versionado de snapshot,
- migraciones explícitas de esquema cuando cambie el canónico,
- fallback conservador y visible, nunca silencioso.

## Riesgos si el lock falla o expira antes de tiempo

1. doble turno simultáneo;
2. `conversation_locked` en OpenAI;
3. lost update al guardar en Redis;
4. trazas fuera de orden;
5. `planner_state` incoherente;
6. turnos duplicados o reordenados para el usuario.

### Mitigación mínima razonable
- lock por sesión con TTL suficientemente largo,
- heartbeat o refresh del lock si el turno supera cierto tiempo,
- compare-and-set o versión de snapshot al guardar,
- logs/metrics para detectar colisiones y expiraciones.

## Conversation ID vs previous_response_id

### Veredicto para este repo
**Mejor `conversation_id`.**

### Por qué
1. El repo ya usa `ThreadMode.conversation` como default.
2. El runtime ya crea/usa `conversation_id`.
3. OpenAI documenta Conversations como mecanismo duradero para Responses.
4. `previous_response_id` es más frágil para una continuidad larga si no replicas cuidadosamente las instrucciones y el threading.

### Cuándo usaría `previous_response_id`
Solo como fallback táctico si:
- no quieres crear objetos `conversation` explícitos,
- tu hilo es muy corto,
- aceptas una continuidad más liviana.

No es lo que recomiendo aquí.

## Qué garantías tendríamos con la migración bien hecha

1. cualquier réplica puede continuar una partida;
2. el pipeline conserva el mismo snapshot táctico;
3. cada usuario queda aislado por `session_id` única;
4. la continuidad OpenAI deja de depender de la RAM local;
5. los residuos por concurrencia bajan de forma fuerte.

## Qué señales vigilar en staging

1. aumento de respuestas que suenan a reinicio;
2. pérdida de referencias a ofertas previas;
3. preguntas repetidas que ya estaban contestadas;
4. cambios extraños de fase;
5. diferencias en trazas antes/después de migrar;
6. locks expirados;
7. retries por `session_busy` o `conversation_locked`.

## Cómo verificar que no se introduce degradación silenciosa

1. golden tests de negociación comparando antes/después;
2. replay de sesiones reales o fixtures sobre ambos stores;
3. diff de trazas en `planner_state`, `negotiation_state`, `recent_dialogue` y `final_reply_text`;
4. tests con restart entre turnos;
5. tests con dos réplicas simuladas usando el mismo Redis;
6. métricas de lock wait, lock timeout y snapshot validation errors.

## Recomendación final honesta

La migración es segura para el flujo **solo si se trata como una migración de snapshot**, no como un simple cambio de “dónde guardar la sesión”.

Si guardas y rehidratas bien el bloque operativo completo, el flujo debería conservar su comportamiento. Si intentas una versión “ligera” que solo guarda `conversation_id` y unas pocas banderas, el resultado más probable es degradación táctica silenciosa.
