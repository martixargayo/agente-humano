# Diagnóstico detallado de archivos **A MEDIAS** y **SIN USO** en `backend/negotiation`

## Objetivo
Este documento baja a nivel de código los elementos clasificados previamente como **A MEDIAS** o **SIN USO**, para responder tres preguntas por cada caso:

1. ¿Se usa en el flujo actual de runtime (grafo `world -> belief -> planner -> executor`)?
2. Si se usa “a medias”, ¿qué partes concretas sí aportan y cuáles no?
3. ¿Hay confirmación suficiente para borrar archivo completo, o solo partes?

## Contexto del flujo actual (referencia)
El runtime principal está orquestado por `negotiation_graph.py` y ejecuta nodos en este orden fijo: `world_updater`, `belief_updater`, `policy_progress`, `phase_policy_planner`, `progress_updater`, `executor`.
Con ese flujo como base, se evalúan los archivos de esta auditoría.

---

## A. Archivos/carpetas **A MEDIAS** (diagnóstico fino)

### 1) `backend/negotiation/__init__.py`
**Estado:** A MEDIAS (estructural)

**Qué sí sirve**
- Define superficie mínima del paquete (`reset_negotiation_llm_caches`) para importación tipo `from negotiation import ...`.

**Qué no aporta al flujo actual**
- El runtime principal importa submódulos directos (`negotiation.negotiation_graph`, etc.); no depende de este re-export para operar.

**Diagnóstico de borrado**
- **No recomendar borrar** completo (rompería ergonomía del paquete).
- **Sí recomendable** mantenerlo minimalista y sin lógica adicional.

---

### 2) `backend/negotiation/belief_state_updater.py`
**Estado:** A MEDIAS (transicional)

**Partes que sí sirven hoy**
- `update_belief_state(...)`: sigue siendo contrato activo en `state/deps.py` (inyección de dependencias), y es usado por tests/harness que mockean o ejercitan esa interfaz.
- `merge_belief_buckets_update_not_rewrite(...)`: se usa en tests específicos de merge/fallback.

**Partes que no participan en runtime principal actual**
- El nodo real de producción (`nodes/belief_node.py`) ya no llama `deps.update_belief_state`; llama directo al extractor `extract_belief_state_llm_v1`.
- `_BeliefDeps` solo vive para la ruta legacy de `update_belief_state`.

**Confirmación**
- Confirmado: **no gobierna** el update belief del flujo principal.
- Confirmado: **sí tiene rol de compatibilidad** para pruebas y contrato de deps.

**Diagnóstico de borrado**
- **No borrar archivo completo** todavía si quieres mantener tests/harness actuales.
- **Candidato a borrado futuro** si migras `state/deps.py` + tests para usar directamente `nodes/belief_node` o un adaptador único.

---

### 3) `backend/negotiation/elementos` (carpeta) y `backend/negotiation/elementos/belief` (subcarpeta)
**Estado:** A MEDIAS (mixto activo+legado)

#### 3.1 Activo dentro de `elementos` (NO borrar)
- `execution_definitions.py` (constantes de outcome usadas por `progress_updater`).
- `strategy_definitions.py` (catálogo de policies/modelos del planner).
- `world_definitions.py` (patrones usados por percepción).
- `render/*` (pipeline de render/executor, constraints y validación).

#### 3.2 Parte legacy dentro de `elementos/belief`
- `belief_contracts.py`: hoy aparece más como soporte de tests/migración histórica.
- `belief_updater_v2_prompts.py`: plantillas de un updater v2 que no participa en el flujo v3 actual.

**Diagnóstico de borrado**
- **No borrar carpeta `elementos`** (rompe runtime).
- Para `elementos/belief/*`: **candidato condicionado** a mover a `legacy/` o eliminar tras migrar tests que dependen de esos contratos.

---

### 4) `backend/negotiation/gating` (carpeta)
**Estado:** A MEDIAS

**Qué sí sirve (activo)**
- `gate_world.py`, `shared.py`, `fingerprints.py` se usan en `world_node`/`gate_utils`.

**Qué no sirve en runtime principal**
- `gate_belief.py`: no está integrado al `belief_updater_node` actual.

**Diagnóstico de borrado**
- **No borrar carpeta**.
- `gate_belief.py`: **candidato a borrar/mover a legacy** si se confirma estrategia de no reintroducir gate de belief.

---

### 5) `backend/negotiation/policy_docs` + archivos `.md`
**Estado:** A MEDIAS (uso potencial condicionado)

**Qué sí sirve**
- Es la ruta por defecto de `rag_dir` en config.
- Si se consume vía tácticas RAG, su contenido puede ser útil.

**Qué está a medias**
- El helper `get_policy_tactics(...)` que consulta ese RAG no está cableado de forma explícita en la ruta principal de nodos.

**Diagnóstico de borrado**
- **No borrar por defecto**: riesgo de quitar contenido estratégico útil/esperado por configuración.
- Si quieres limpiar, primero decide: o se integra RAG táctico en planner/executor, o se desactiva y entonces sí puedes retirar estos docs.

---

## B. Archivos/carpetas **SIN USO** (confirmación y propuesta)

## B1) Confirmados sin rol runtime y sin lógica crítica (borrado de bajo riesgo)

### 1) `backend/negotiation/contracts_v2.py`
- Archivo de contratos/constantes amplio, pero sin integración visible en el flujo actual.
- **Confirmación:** sin papel operativo en runtime principal.
- **Acción sugerida:** candidato fuerte a borrar completo (o mover a `legacy/` si se quiere histórico).

### 2) `backend/negotiation/elementos/belief_definitions.py`
- Modelado Pydantic/config de belief v2 no conectado a la tubería actual.
- **Confirmación:** sin uso runtime actual.
- **Acción sugerida:** borrar o mover a legacy junto con `elementos/belief/*`.

### 3) `backend/negotiation/gating/gate_belief.py`
- Lógica de gate belief existente, pero no invocada por el nodo belief actual.
- **Confirmación:** sin uso en runtime principal (sí aparece en tests).
- **Acción sugerida:**
  - Opción A: integrar de nuevo en `belief_node`.
  - Opción B (limpieza): borrar + ajustar tests.

### 4) Namespaces vacíos / `__init__.py` vacíos
- `extractors/__init__.py`, `gating/__init__.py`, `graph/__init__.py`, `nodes/__init__.py`, `perception/__init__.py`, `planner/__init__.py`, `progress/__init__.py`, `state/__init__.py`, `telemetry/__init__.py`.
- **Confirmación:** no contienen lógica de negocio (rol puramente de paquete).
- **Acción sugerida:**
  - Si no necesitas namespace package explícito, pueden borrarse sin impacto funcional.
  - Si prefieres estabilidad/importabilidad, mantenerlos también es válido.

### 5) `backend/negotiation/graph` y `backend/negotiation/planner` y `backend/negotiation/progress` (carpetas vacías)
- Son namespaces sin implementación activa dentro.
- **Confirmación:** no participan en runtime actual.
- **Acción sugerida:** candidatos a borrar para reducir ruido estructural.

---

## B2) SIN USO en runtime pero con valor documental (borrado opcional)

### 6) `backend/negotiation/config/README.md`
- No ejecuta lógica.
- **Acción:** mantener si sirve de guía operativa; borrar si está desactualizado.

### 7) `backend/negotiation/phase_docs/*`
- Documentación de fases no conectada directamente al flujo actual.
- **Acción:** mantener como base conceptual, o mover a `docs/legacy/`.

---

## C. Confirmación de “partes de código a borrar” (granular)

### C1) Borrado recomendado (alta confianza)
1. `contracts_v2.py` completo.
2. `elementos/belief_definitions.py` completo.
3. Carpetas namespace vacías `graph/`, `planner/`, `progress/` y `__init__.py` vacíos asociados (si no hay política de mantenerlos).

### C2) Borrado condicionado (requiere decisión de producto/arquitectura)
1. `gating/gate_belief.py` (depende de si reintroducirás belief gating).
2. `belief_state_updater.py` (depende de si mantienes contrato `deps.update_belief_state` para tests/harness).
3. `elementos/belief/*` (depende de migración de tests legados).
4. `policy_docs/*` (depende de si el RAG táctico se integra de forma explícita o se descontinúa).
5. `phase_docs/*` y `config/README.md` (documentación; decisión de gobierno documental).

---

## D. Plan de limpieza propuesto (seguro y en etapas)

### Etapa 1 (rápida, bajo riesgo)
- Eliminar namespaces vacíos y `__init__.py` sin contenido útil.
- Eliminar `contracts_v2.py` y `elementos/belief_definitions.py`.

### Etapa 2 (con ajuste de tests)
- Decidir destino de `gate_belief.py`.
- Decidir destino de `belief_state_updater.py` + adaptación de `state/deps.py` y harnesses.

### Etapa 3 (producto/documentación)
- Decidir si `policy_docs/*` entra formalmente en planner/executor; si no, archivar/eliminar.
- Reubicar o podar `phase_docs/*`.

---

## E. Resultado final para toma de decisión

Este diagnóstico confirma que sí hay un bloque pequeño pero real de **código eliminable** (con alta confianza), y otro bloque **transicional** que hoy estorba claridad arquitectónica pero requiere una decisión previa para no romper tests ni capacidades futuras.
