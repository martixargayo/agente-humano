# PR2: World extractor v2

## Qué problema resuelve
Este PR separa la evidencia universal y los claims abiertos del dominio de negociación sin romper el `WorldState` actual. Se evitan pérdidas de información cuando la conversación no es negociación y se mantiene la compatibilidad con los campos legacy de precio/urgencia. Además, se añade una vía de extracción LLM v2 con validación estricta para evitar claves arbitrarias y datos fuera de rango.

## Por qué `domain_patch` y `universal_patch` van separados
- **`domain_patch`** preserva el esquema legacy de negociación y evita contaminar conversaciones generales con campos específicos (precio, plazos, etc.).
- **`universal_patch`** captura evidencia transversal (metas, constraints, entidades, actos de habla) que aplica a cualquier dominio.
- Esta separación permite evolucionar el extractor y el esquema universal sin romper el pipeline de negociación existente.

## Por qué `open_claims` es “cerrado”
Aunque es open-world en contenido, el formato es cerrado (label regex, enums, límites y dedupe) para evitar roturas del schema, explosión de memoria o keys arbitrarias. Esto permite flexibilidad con control: etiquetas estables y límites globales.

## Por qué el merge es conservador
El merge conservador reduce oscilaciones y evita borrar evidencia previa con parches de menor confianza. Se prioriza el objetivo con mayor confidence y se deduplica por claves semánticas, manteniendo orden y límites estrictos para estabilidad.

## Cómo afecta a la universalidad del sistema
Con `universal_state` y `open_claims`, el sistema puede operar en modo “general” sin perder estructura, y mantener señales relevantes en conversaciones no negociadoras. El extractor v2 consolida esta evidencia y abre el camino a módulos universales sin acoplarlos a negociación.
