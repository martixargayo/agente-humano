# Auditoría profunda (avatar negociación vs optimizador canónico)

## Resultado técnico actual
- **Motor central único**: `run_negotiation_turn_canonical`.
- **Primer punto de divergencia real (actual)**: `channel` (`avatar` vs `optimizer`) y endpoint de entrada (`/api/negotiation/turn` vs `/api/optimizador/sandbox/turn`).
- **Divergencia corregida en esta iteración**: el avatar ya no reescribe `session_id` con prefijo oculto `neg::`; usa el `session_id` canónico tal cual.

## Hipótesis investigadas y evidencia
1. **¿Avatar no usa el flujo canónico?**
   - Sí usa el flujo canónico en negociación: `/api/negotiation/turn -> _run_canonical_negotiation -> run_negotiation_turn_canonical`.
2. **¿Avatar mezcla rutas?**
   - Antes coexistían `/chat` y negociación en el frontend avatar.
   - Ahora el frontend avatar quedó en **negociación-only** para evitar contaminación por chat.
3. **¿Reset/new conversation no limpia?**
   - `new_conversation` en avatar hace reset de sesión previa y crea nueva sesión.
4. **¿Audio altera lógica negociadora?**
   - STT/TTS siguen como capas I/O; la negociación entra/sale en texto.
   - Se bloqueó el bypass de respuestas demo en modo negociación para evitar saltarse backend canónico.
5. **¿Optimizador comparado estaba en modo más rico?**
   - Sí puede usar overrides/experimental en `sandbox/turn`; comparación correcta debe hacerse con `resolved_entries=[]` (modo canónico).
6. **¿Diferencias de estado/thread/config?**
   - Se añadió `trace_probe` en respuesta de negociación para inspección directa de hashes y contexto de threading.

## Cambios aplicados en esta iteración (sin tocar semántica del optimizador)
- Avatar negociación:
  - modo por defecto `NEGOTIATION` y bloqueo de modo chat en runtime.
  - envío forzado a `/api/negotiation/turn` canónico.
  - desactivado bypass demo (skip backend) cuando el modo es negociación.
- Backend negociación avatar:
  - eliminado namespacing oculto `neg::` en resolución de sesión para canal avatar.
  - exposición de `trace_probe` para comparar hashes/contexto del turno.

## Lo que sigue siendo distinto (intencional)
- Endpoint de entrada y `channel` difieren entre avatar y optimizador.
- El optimizador conserva capacidades experimentales (overrides) que no se han tocado.
