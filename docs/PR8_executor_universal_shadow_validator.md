# PR8: Executor universal + perfiles de render + validator shadow-mode

## Qué problema resuelve
El executor mezclaba rendering con estrategia y el validator reescribía la salida, generando inestabilidad y comportamiento difícil de explicar. Ahora se separa **qué se hace** (strategy) de **cómo se dice** (render), y el validator deja de reescribir salvo violaciones críticas.

## Qué cambia
- **Executor universal**: renderiza a partir de `policy_id` + `micro_goal` + `why_short` + `precedence` sin replanificar. El output es JSON estable (`ExecutorOutput`) y se guarda además un `assistant_message` legacy para compatibilidad.
- **Perfiles inyectables**: `persona_profile`, `scene_profile` y `style_contract` viven en `ProgressState` y se normalizan. El executor los usa sin inferirlos del usuario.
- **Constraints estructurados**: `RenderConstraints` se construyen de forma determinista (p. ej. sin números si hay guard de negociación) y se pasan al render.
- **Validator shadow-mode**: registra violaciones pero **no reescribe**, salvo en casos críticos (acceso interno, acciones físicas, leaks, instrucciones peligrosas). El fallback es determinista.

## Cómo se aplica
1. `strategy_summary` se construye en el executor node para traza (policy, micro_goal, risk_posture, precedence_reason, etc.).
2. Se renderiza con `persona/scene/style` y `constraints_struct` usando un prompt fijo que retorna JSON.
3. El output se normaliza y se guarda en `executor_output` y `assistant_message` (legacy).
4. El validator evalúa en shadow-mode; solo en violaciones críticas aplica fallback duro.

## POR QUÉ
- **Separación de responsabilidades**: evita que el executor cambie estrategia y que el validator “corrija” el mensaje salvo casos críticos.
- **Estabilidad multi-dominio**: el executor funciona para conversación general o negociación con el mismo contrato.
- **Observabilidad**: `executor_output` + `executor_validator_meta` permiten telemetría sin alterar la respuesta.
- **Extensibilidad**: nuevos perfiles o escenas se inyectan sin tocar el planner.
