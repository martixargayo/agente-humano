# PR3: BeliefState v2 universal + negotiation

## Problema actual
El belief estaba acoplado a negociación y no representaba de forma consistente señales universales (tensión, loop, evasión) en conversaciones generales. Esto obligaba a inventar señales o a ignorarlas.

## Solución propuesta
Se introduce un **BeliefState v2** con dos capas:
- **universal**: métricas, dinámica, ToM y razones válidas para cualquier dominio.
- **negotiation**: contenedor para el belief específico de negociación.

Además, se mantienen **mirrors legacy** (`dynamics`, `tom`, `stance`, etc.) para evitar refactors cascada en planner/strategy.

## Por qué mirrors legacy
Mantener los campos actuales evita romper consumidores existentes y permite migraciones graduales. Los mirrors apuntan a la capa universal/negotiation, preservando compatibilidad.

## Por qué clamps y límites
Los clamps evitan oscilaciones bruscas en métricas y reducen inestabilidad inter-turno. Los límites en ToM y razones previenen crecimiento sin control y aseguran consistencia.

## Cómo gate_belief universal evita ceguera
El gate ahora abre cuando hay señales universales reales (escalation, loop, evasión o cambios en universal_state). Esto evita que el belief quede congelado en conversaciones tensas o con evidencia nueva fuera del dominio de negociación.
