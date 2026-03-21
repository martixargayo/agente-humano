# ACK correlacionado del guardado embebido

## Objetivo

Endurecer el ACK `final_result_saved` para que el toast local **“Resultados guardados”** solo aparezca cuando el mensaje recibido desde el padre esté realmente correlacionado con el último `final_result` emitido por la instancia embebida actual.

## Riesgo previo

Antes de este ajuste, el simulador aceptaba el ACK si el mensaje:

- venía del origin permitido;
- tenía `ns` y `v` correctos;
- tenía `type = final_result_saved`;
- y `payload.status === 'ok'` o `payload.saved === true`.

Ese criterio era insuficiente porque no exigía correlación contra el último `final_result` pendiente. Un ACK tardío, cruzado o espurio podía activar el toast incorrectamente.

## Flujo auditado

### Construcción del `final_result`

El payload final se construye en `buildFinalResultPayload(report, extra)`.

### Emisión del `final_result`

La emisión se realiza en `emitFinalResultLifecycle(report, { reason })`.

### Estado pendiente de ACK

Con este ajuste, tras emitir `final_result`, el simulador registra en memoria el último guardado pendiente con estos campos:

- `session_id`
- `activityid`
- `evaluation_id`
- `payload_hash`
- `correlation_id`
- `event_id`
- `emitted_at_ms`
- `emitted_at_iso`
- `pending_ack`
- `ack_confirmed`
- metadatos del último ACK aceptado

## Criterio exacto de aceptación

El simulador acepta `final_result_saved` solo si se cumplen **todas** estas condiciones:

1. `origin` permitido;
2. `ns = gestionce.simulator`;
3. `v = 1`;
4. `type = final_result_saved`;
5. `payload.status === 'ok'` o `payload.saved === true`;
6. existe un `final_result` pendiente;
7. coincide `session_id`;
8. coincide `activityid`;
9. y además coincide al menos **uno** de estos identificadores fuertes:
   - `evaluation_id`
   - `payload_hash`
   - `correlation_id`

Si no se cumple todo lo anterior, el ACK se rechaza y el toast no aparece.

## Identificadores usados

### `payload_hash`

El simulador calcula un `payload_hash` estable sobre el contenido relevante del `final_result` y lo incluye dentro del propio payload final.

### `correlation_id`

El `final_result` ya no usa un `correlation_id` genérico de bootstrap para el mensaje final. Ahora se emite con una correlación específica del resultado final basada en:

- `session_id`
- `evaluation_id`
- `payload_hash`

Esto reduce el riesgo de aceptar ACKs cruzados entre varios informes emitidos dentro de la misma sesión embebida.

## ACK duplicados y tardíos

### ACK duplicado

Si llega dos veces el mismo ACK ya confirmado para el último `final_result`, el simulador:

- no muestra un segundo toast;
- no reabre el estado de guardado;
- solo deja traza en consola como ACK repetido.

### ACK tardío o cruzado

Si ya se emitió un nuevo `final_result`, el estado pendiente se reemplaza por el más reciente.

Por tanto, un ACK viejo:

- aunque tenga el mismo `session_id`;
- aunque tenga el mismo `activityid`;
- no será aceptado si ya no coincide con ningún identificador fuerte del último guardado pendiente.

## Shape esperado del ACK

Ejemplo aceptado:

```json
{
  "ns": "gestionce.simulator",
  "v": 1,
  "type": "final_result_saved",
  "payload": {
    "status": "ok",
    "session_id": "sess-001",
    "activityid": "negociacion",
    "evaluation_id": "eval-123",
    "payload_hash": "fnv1a:b37ad019",
    "correlation_id": "sess-001:final:eval-123:fnv1a:b37ad019",
    "entryid": "278",
    "version": "1"
  }
}
```

### Metadatos opcionales

Si el padre envía `entryid` y/o `version`, se conservan como metadatos del último guardado confirmado.

## Casos rechazados

Se rechaza el ACK si ocurre cualquiera de estos casos:

- no hay `final_result` pendiente;
- `origin` no permitido;
- `session_id` distinto;
- `activityid` distinto;
- no coincide ninguno entre `evaluation_id`, `payload_hash` y `correlation_id`;
- ACK duplicado del mismo guardado ya confirmado;
- ACK viejo de una emisión anterior después de un nuevo `final_result`.

## Logs diagnósticos añadidos

Se añadieron logs explícitos para:

- ACK recibido;
- ACK rechazado por `origin`;
- ACK ignorado porque no hay pendiente;
- ACK rechazado por `session_id`;
- ACK rechazado por `activityid`;
- ACK rechazado por falta de correlación fuerte;
- ACK aceptado;
- ACK repetido;
- toast mostrado.

## Tests ejecutados

Se amplió el harness automático para cubrir:

- ACK válido correlacionado;
- `session_id` incorrecto;
- `activityid` incorrecto;
- correlación fuerte ausente;
- ACK duplicado;
- ausencia de pendiente;
- ACK tardío del intento anterior;
- aceptación del ACK del último intento activo.

## Riesgos remanentes

1. El padre debe reenviar los identificadores de correlación para que el endurecimiento sea plenamente efectivo en producción.
2. Si el integrador solo reenvía `session_id` y `activityid`, el simulador rechazará el ACK por diseño.
3. Este ajuste protege la instancia cliente actual; no sustituye una auditoría completa en el lado Moodle si hubiese múltiples iframes concurrentes.
