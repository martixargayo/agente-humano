# Ajuste visual del botón "Finalizar conversación"

## Diagnóstico realizado

### Estado que activa hoy el highlight
El estado funcional del botón se controla con `finishButtonArmed` en `backend/interfaz_usuario_app/app.js`.

- `armFinishButton(nextArmed)` lo activa cuando backend devuelve `finish_button_armed`.
- `resetFinishButtonArmed()` lo limpia al cambiar de sesión.
- `updateFinishNegotiationButton()` refleja el estado en clases CSS del botón.

### Dónde se renderiza
El botón se renderiza en `backend/interfaz_usuario_app/index.html` como `#finishNegotiationBtn`.

### Qué causaba el recorte del glow
La causa real no era un pseudo-elemento incorrecto ni un `overflow: hidden` de un contenedor intermedio del propio botón.

El problema era esta combinación:

1. El glow del botón se aplicaba directamente al propio botón con `box-shadow` en `.finish-negotiation-button.is-armed`.
2. El botón estaba anclado como `position: fixed` a solo `24px` del borde inferior y derecho de la ventana.
3. En el layout principal, `html, body` usan `overflow: hidden`, por lo que cualquier sombra que se expanda fuera del viewport queda recortada.
4. Como la expansión del glow necesitaba espacio extra justo hacia abajo y hacia la derecha, el halo quedaba visualmente cortado en esos lados.

### Por qué no se parecía al botón de referencia
El botón de referencia de Enter / enviar mensaje usa una combinación más contenida y limpia:

- un borde más suave,
- una sombra más controlada,
- y suficiente aire visual alrededor dentro de la barra inferior.

En cambio, el botón de finalizar conversación intentaba resolver todo con un `box-shadow` sobre un botón pegado al borde del viewport. Eso producía un halo truncado, especialmente perceptible en la esquina inferior derecha.

## Solución aplicada

### Separación de estados
Se han separado claramente cuatro capas de comportamiento:

1. **Estado funcional**: `finishButtonArmed`.
2. **Estado visual persistente**: clase `is-highlighted`.
3. **Animación temporal de atención**: clase `is-attention-active` durante 5 segundos.
4. **Temporizador de control**: `finishButtonHighlightTimer`.

### Cambios visuales

#### 1. Glow persistente limpio
En lugar de depender solo de `box-shadow`, ahora el glow azul se construye con un `::before` en el propio botón:

- gradiente radial azul,
- blur suave,
- opacidad controlada por variable CSS,
- sin borde azul duro ni outline artificial.

Esto permite un halo más parecido al acabado visual del botón de referencia.

#### 2. Espacio real para que el glow no se recorte
El botón ahora vive dentro de `.finish-negotiation-button-wrap`, anclado con una separación segura mayor respecto al borde del viewport.

Eso evita que el halo tenga que “salirse” de la pantalla para verse completo. Con ello desaparece el recorte visible del glow.

#### 3. Pulso temporal de 5 segundos
Cuando el botón pasa de desarmado a armado:

- el glow se activa inmediatamente,
- se lanza `finishNegotiationPulse`,
- la animación dura exactamente 5 iteraciones de 1 segundo,
- al completarse, el pulso se detiene,
- el glow persistente se mantiene mientras el botón siga armado.

### Política aplicada si el estado se reactiva
Criterio implementado:

- **Solo se reinicia la animación cuando el botón pasa de no armado a armado**.
- Si el backend vuelve a enviar `true` mientras ya estaba armado, **no se reinicia** el pulso.
- Si el estado se limpia y más adelante vuelve a activarse, entonces **sí vuelve a arrancar** el ciclo completo de 5 segundos.

Esto evita timings frágiles y animaciones molestas repetidas sobre un botón que ya estaba resaltado.

## Accesibilidad y robustez

- No se ha cambiado la semántica del botón ni su interacción de teclado.
- El glow no desplaza layout porque se resuelve con pseudo-elemento y transformaciones visuales.
- El pulso es pequeño y no modifica flujo de documento.
- Se ha añadido un comportamiento para `prefers-reduced-motion: reduce`, desactivando la animación temporal pero manteniendo el estado visual estable.
- El estado persistente sigue funcionando aunque el temporizador termine.

## Comprobaciones manuales recomendadas

1. Entrar en el flujo normal hasta cumplir los requisitos para finalizar la conversación.
2. Observar que al armarse el botón aparece el glow azul inmediatamente.
3. Confirmar que durante 5 segundos hace un pulso suave, visible y no brusco.
4. Confirmar que al terminar esos 5 segundos el pulso desaparece.
5. Confirmar que el glow azul sigue estable mientras el botón continúe armado.
6. Confirmar que, al resetear sesión o perder el estado armado, desaparecen glow y animación.
7. Comparar visualmente el glow con el botón de Enter / enviar mensaje: ahora el halo debe verse limpio y no truncado.
