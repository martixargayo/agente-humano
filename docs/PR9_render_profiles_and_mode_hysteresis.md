# PR9: Perfiles de render + constraints_struct por turno + histéresis de conversation_mode

## Qué problema resuelve
El executor ya es universal (PR8), pero aún faltaba fijar **contratos exactos** para perfiles de render y separar lo **persistente de sesión** frente a lo **derivado por turno**, además de estabilizar `conversation_mode` para evitar oscilaciones.

## Qué cambia
- **RenderState persistente** en `ProgressState`: ids de persona/scene/style y language, sin inferencias del texto del usuario.
- **Constraints_struct derivado por turno**: se construye determinísticamente con reglas de producto + estado (tensión, modo, guardas) y se guarda por turno para el executor/validator.
- **Histéresis de conversation_mode**: el modo se actualiza con score suavizado y umbrales distintos para subir/bajar, evitando flip-flop por señales débiles.

## Cómo funciona
1. `render_state` mantiene ids estables (persona/scene/style) a nivel sesión.
2. `resolve_render_profiles` resuelve perfiles por id sin leer el user text.
3. `build_constraints_struct` deriva constraints por turno (markdown, max_questions, disallow_numbers, slots mínimos).
4. El modo se actualiza con `update_conversation_mode` y se persiste con `mode_confidence` y `mode_last_switch_turn`.

## POR QUÉ
- **Perfiles como inputs estables**: previene drift y mezcla de estrategia en el rendering.
- **Constraints deterministas**: control y auditabilidad; el executor obedece reglas claras sin LLM.
- **Histéresis en mode**: evita oscilaciones por señales débiles o ruidosas.
- **Compatibilidad**: `assistant_message` sigue siendo el output textual legacy; se mantiene el pipeline actual.
- **Encaje PR7/PR8**: perfiles + constraints alimentan el executor universal, y el mode estable es el input para packs/precedence sin contaminar strategy.
