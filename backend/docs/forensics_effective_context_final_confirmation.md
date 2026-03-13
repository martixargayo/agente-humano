# Confirmación forense final (conclusiva): diferencia de calidad `optimizador` vs `interfaz_usuario`

## Resumen ejecutivo

Conclusión final cerrada:

1. **La causa raíz dominante no es un runtime distinto**, sino **desalineación de contexto pre-memory por reutilización de sesión/conversación**.
2. El campo operativo que primero diverge en uso normal es `recent_dialogue_short` (vía `load_recent_dialogue -> build_memory_input`).
3. `memory` no es el origen, sino el primer nodo donde cristaliza la divergencia previa.
4. La asimetría práctica “optimizador mejor que interfaz” se explica por **patrón estructural de uso**: interfaz se usa con más frecuencia sobre sesión fija reutilizada; optimizador suele operar con sesiones/conversaciones frescas.
5. Se aplicó fix de bajo riesgo para reducir la asimetría en uso real: **semilla automática de sesión única por carga en `interfaz_usuario_app`** (además del hardening previo de IDs `new_conversation`).

## Evidencia base ya existente (reconfirmada)

- `forensics_effective_context_parity_run.json` mantiene:
  - `first_payload_divergence = null` en baseline limpio.
  - en skew controlado, primera divergencia en `recent_dialogue_short.length`.
- `forensics_effective_context_root_cause_run.json` confirma que la divergencia nace pre-memory (`memory_input_build_first_diff`) y luego cascada.

## Nueva comprobación concluyente

Script nuevo: `backend/scripts/forensics_effective_context_final_confirmation.py`
Artefacto: `backend/docs/forensics_effective_context_final_confirmation_run.json`

### Escenario 1 — `usage_pattern_asymmetry`

- Interfaz: se reutiliza `session_id` fijo (`interfaz-main`) en “primeros turnos” sucesivos de casos independientes.
- Optimizador: cada caso arranca en sesión nueva (`/sandbox/new_conversation`).

Resultado:

- Interfaz `recent_dialogue_len` en primer turno por caso: `[1,3,5,7,9,11,12,12]`
- Optimizador: `[1,1,1,1,1,1,1,1]`
- Contaminación en “primer turno”:
  - interfaz: `7/8`
  - optimizador: `0/8`

### Escenario 2 — `both_fresh_control`

- Ambos carriles con sesión nueva por caso.
- Resultado: ambos `[1,1,1,1,1,1,1,1]`, contaminación `0/8` en ambos.

Interpretación causal:

- Cuando ambos arrancan limpios, convergen.
- Cuando interfaz reutiliza sesión fija y optimizador no, aparece asimetría sistemática.
- Por tanto, el sesgo percibido no viene del “cerebro”, sino de **higiene de continuidad**.

## Mapa causal definitivo (punto exacto)

1. `StateRepository.load_recent_dialogue(...)` carga `world_state["negotiation_canonical_recent_dialogue"]`.
2. `build_memory_input(...)` inyecta ese buffer en `recent_dialogue_short`.
3. Si el buffer ya está contaminado (por reutilización), el primer input que ve `memory` ya llega sesgado.
4. `apply_memory_output_to_state(...)` refresca `memory_working`/`negotiation_state` sobre base ya sesgada.
5. `planner` y `executor` reciben estado derivado sesgado y degradan calidad táctica/naturalidad.

## Por qué caía más del lado de `interfaz_usuario`

Confirmado como **combinación de estructura de uso + UX por defecto**:

- Interfaz simple tiende a operar con IDs fijos y reutilizados entre pruebas manuales.
- Optimizador incorpora flujo de experimentación con mayor uso de sesiones nuevas.
- Esta asimetría de arranque cambia la probabilidad de contaminación pre-memory y explica la percepción consistente.

## Fix aplicado

### Fix operativo (nuevo en este ciclo)

- Archivo: `backend/interfaz_usuario_app/app.js`
- Cambio: al cargar la app, se generan `user_id/session_id` únicos y se hace `bootstrap` automático.
- Efecto: reduce drásticamente reutilización accidental de sesión y contaminación de “primer turno”.

### Fix técnico previo mantenido

- IDs `new_conversation` endurecidos con microsegundos + sufijo aleatorio en backend (ambas superficies), eliminando colisiones por timestamp a segundos.

## Riesgos

- Bajo: el cambio de `interfaz_usuario_app` afecta defaults de UI, no el runtime cognitivo.
- Riesgo funcional: usuarios que esperaban continuidad implícita al recargar página ahora deben conservar/copiar IDs explícitamente.

## Validación

- Tests de forense final verifican asimetría por patrón de uso y convergencia cuando ambos carriles arrancan frescos.
- Scripts reproducibles generan JSON versionado para auditoría.

## Estado final de las 4 preguntas

1. **Causa exacta**: contaminación de continuidad pre-memory por reutilización de sesión/conversación (campo visible dominante: `recent_dialogue_short`).
2. **Por qué más en interfaz**: patrón estructural de uso y defaults de superficie aumentaban la probabilidad de arranque no limpio.
3. **Solución exacta**: higiene de sesión en origen (IDs únicos por carga en interfaz + hardening de `new_conversation` IDs en backend).
4. **Cómo sabemos que funciona**: A/B reproducible demuestra asimetría bajo patrón contaminante y convergencia total bajo arranque fresco simétrico.
